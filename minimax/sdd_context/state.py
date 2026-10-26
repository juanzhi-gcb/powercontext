"""Task state persistence through a running PowerContext server.

A task owns one PowerContext Scope. Every state transition is appended as an
Atomic Memory entry of kind ``sdd-task-state``; the newest entry (by the
``updated_at`` field inside the payload) is the current state. Nothing is kept
in the module's own memory, so a restarted module reads the same record back
from PowerContext.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

STATE_KIND = "sdd-task-state"
MILESTONE_KIND = "sdd-milestone"


class PowerContextError(RuntimeError):
    """Raised when the PowerContext server rejects a request."""


class PowerContextState:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 20.0,
        recorder: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.recorder = recorder

    # -- transport -----------------------------------------------------
    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body) if body else {}
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise PowerContextError(f"{method} {path} -> HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise PowerContextError(
                f"PowerContext is not reachable at {self.base_url} ({exc.reason}); "
                "start it with scripts/start_powercontext.sh"
            ) from exc
        if self.recorder is not None:
            self.recorder.record(
                {
                    "method": method,
                    "path": path,
                    "status": status,
                    "request": payload,
                    "response": result,
                }
            )
        return result

    def healthy(self) -> bool:
        try:
            self._request("GET", "/health/live")
            return True
        except PowerContextError:
            return False

    # -- scopes --------------------------------------------------------
    def ensure_scope(self, *, title: str, summary: str) -> str:
        """Create the task Scope, or find the one created by an earlier run."""

        try:
            descriptor = self._request(
                "POST",
                "/v1/scopes",
                {
                    "title": title[:256],
                    "summary": summary[:2000],
                    "idempotency_key": title[:256],
                },
            )
            return descriptor["scope_id"]
        except PowerContextError as exc:
            if "HTTP 409" not in str(exc):
                raise
        page = self._request(
            "GET", "/v1/scopes?query_field=title&query=" + urllib.parse.quote(title)
        )
        items = page.get("items") or []
        for item in items:
            if item.get("title") == title:
                return item["scope_id"]
        raise PowerContextError(f"scope {title!r} exists but cannot be resolved")

    def get_scope(self, scope_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/scopes/{scope_id}")

    def find_scope(self, title: str) -> str | None:
        """Look up an existing task Scope without creating one."""

        page = self._request(
            "GET", "/v1/scopes?query_field=title&query=" + urllib.parse.quote(title)
        )
        for item in page.get("items") or []:
            if item.get("title") == title:
                return item["scope_id"]
        return None

    # -- memory --------------------------------------------------------
    def remember(self, scope_id: str, kind: str, text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/memory/remember",
            {"scope_id": scope_id, "kind": kind, "text": text},
        )

    def list_entries(self, scope_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "POST",
            "/v1/memory/entries/list",
            {"scope_id": scope_id, "limit": limit},
        )
        return list(response.get("entries") or [])

    def write_state(self, scope_id: str, state: dict[str, Any]) -> dict[str, Any]:
        payload = dict(state)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        previous = self.read_state(scope_id)
        payload["seq"] = int(previous.get("seq", 0)) + 1 if previous else 1
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode("utf-8")) > 8000:
            text = json.dumps(_compact(payload), ensure_ascii=False, separators=(",", ":"))
        response = self.remember(scope_id, STATE_KIND, text)
        payload["_artifact"] = _first_artifact(response)
        return payload

    def read_state(self, scope_id: str) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for entry in self.list_entries(scope_id):
            if entry.get("kind") != STATE_KIND:
                continue
            try:
                parsed = json.loads(entry.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            parsed["_artifact"] = entry.get("artifact")
            candidates.append(parsed)
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.get("updated_at") or "", item.get("seq") or 0))
        return candidates[-1]

    def milestone(self, scope_id: str, text: str) -> dict[str, Any]:
        return self.remember(scope_id, MILESTONE_KIND, text[:8000])


def _first_artifact(response: dict[str, Any]) -> Any:
    records = response.get("records") or []
    if records:
        return records[0].get("artifact")
    return None


def _compact(state: dict[str, Any]) -> dict[str, Any]:
    compact = dict(state)
    compact.pop("context", None)
    return compact


class RequestRecorder:
    """Write every PowerContext exchange to a JSONL evidence file."""

    def __init__(self, path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry["at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")