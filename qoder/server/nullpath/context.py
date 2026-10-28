from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings


class PowerContextUnavailable(RuntimeError):
    pass


def artifact_text(record: dict[str, Any]) -> str:
    content = record.get("content", record)
    return content.get("text", "") if isinstance(content, dict) else ""


def artifact_ref(record: dict[str, Any]) -> dict[str, Any]:
    artifact = record.get("artifact") or record
    return {
        "artifact_id": artifact.get("artifact_id"),
        "revision": artifact.get("revision"),
    }


class PowerContextAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._scope_id = settings.powercontext_scope_id

    @property
    def configured(self) -> bool:
        return bool(self.settings.powercontext_url)

    @property
    def scope_id(self) -> str:
        if not self._scope_id:
            payload, _ = self.request(
                "POST",
                "/v1/scopes",
                {
                    "title": "NullPath Research CI",
                    "summary": "Research constraints, active pointers, and handoffs; facts remain in seekdb",
                    "idempotency_key": "nullpath-research-ci-v1",
                },
            )
            self._scope_id = payload["scope_id"]
        return self._scope_id

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        etag: str | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        if not self.configured:
            raise PowerContextUnavailable("POWERCONTEXT_URL is not configured")
        headers = {"Content-Type": "application/json"}
        if self.settings.powercontext_token:
            headers["Authorization"] = f"Bearer {self.settings.powercontext_token}"
        if etag:
            headers["If-Match"] = etag
        request = Request(
            f"{self.settings.powercontext_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                body = json.load(response) if response.status != 204 else {}
                return body, response.headers.get("ETag")
        except (HTTPError, URLError, TimeoutError) as error:
            detail = ""
            if isinstance(error, HTTPError):
                detail = error.read().decode(errors="replace")[:1000]
            raise PowerContextUnavailable(
                f"PowerContext {method} {path} failed: {error} {detail}"
            ) from error

    def list_kind(self, kind: str) -> list[dict[str, Any]]:
        payload, _ = self.request(
            "POST",
            "/v1/atomic-memory/list",
            {"scope_id": self.scope_id, "kind": kind, "limit": 20},
        )
        return payload.get("items", [])

    def save_state(self, kind: str, text: str) -> dict[str, Any]:
        scope = self.scope_id
        existing = self.list_kind(kind)
        if existing:
            ref = artifact_ref(existing[0])
            current, etag = self.request(
                "GET", f"/v1/scopes/{scope}/artifacts/atomic-memory/{ref['artifact_id']}"
            )
            updated, _ = self.request(
                "PUT",
                f"/v1/scopes/{scope}/artifacts/atomic-memory/{ref['artifact_id']}",
                {"content": {"kind": kind, "text": text}},
                etag,
            )
            return updated or current
        created, _ = self.request(
            "POST",
            f"/v1/scopes/{scope}/artifacts",
            {
                "family": "atomic-memory",
                "content": {
                    "schema": "powercontext.atomic-memory.v1",
                    "kind": kind,
                    "text": text,
                },
            },
        )
        return created

    def load_active(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for kind in (
            "research_constitution",
            "active_research_contract",
            "active_pointer",
            "handoff",
            "secretary_context",
        ):
            for record in self.list_kind(kind):
                text = artifact_text(record)
                if kind == "secretary_context":
                    try:
                        if not json.loads(text).get("accepted_lines"):
                            continue
                    except (json.JSONDecodeError, AttributeError):
                        continue
                entries.append(
                    {
                        "kind": kind,
                        **artifact_ref(record),
                        "text": text,
                    }
                )
        return entries

    def load_exact(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scope = self.scope_id
        entries = []
        for ref in refs:
            record, _ = self.request(
                "GET",
                f"/v1/scopes/{scope}/artifacts/atomic-memory/{ref['artifact_id']}"
                f"/revisions/{ref['revision']}",
            )
            entries.append({**ref, "text": artifact_text(record)})
        return entries

    @staticmethod
    def references(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "artifact_id": entry["artifact_id"],
                "revision": entry["revision"],
                "kind": entry["kind"],
                "sha256": hashlib.sha256(entry.get("text", "").encode()).hexdigest(),
            }
            for entry in entries
            if entry.get("artifact_id") and entry.get("revision")
        ]

    def save_pointer(self, attempt_id: str, run_id: str, decision: str) -> dict[str, Any]:
        text = json.dumps(
            {"attempt_id": attempt_id, "run_id": run_id, "decision": decision},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        record = self.save_state("active_pointer", text)
        return {**artifact_ref(record), "kind": "active_pointer"}

    def save_handoff(self, completed: str, unresolved: str, next_action: str) -> dict[str, Any]:
        text = json.dumps(
            {"completed": completed, "unresolved": unresolved, "next_action": next_action},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return self.save_state("handoff", text)

    def status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "not_configured",
                "scope_id": None,
                "message": "Set POWERCONTEXT_URL to enable persistent research context",
            }
        try:
            entries = self.load_active()
            return {
                "status": "ready",
                "scope_id": self.scope_id,
                "entries": entries,
                "references": self.references(entries),
            }
        except PowerContextUnavailable as error:
            return {
                "status": "unavailable",
                "scope_id": self._scope_id or None,
                "message": str(error),
            }
