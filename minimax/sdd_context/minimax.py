"""MiniMax client and change application.

The model receives the selected specification items, the code excerpts and the
tests straight from the context package. It answers with a JSON document that
replaces whole files; the module validates the paths and syntax, writes the
files, and records the resulting unified diff as evidence.
"""

from __future__ import annotations

import ast
import difflib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .select import context_for_prompt

SYSTEM_PROMPT = """你是一名严格遵守规格的资深 Python 工程师，正在完成一次规格驱动开发（SDD）任务。

规则：
1. 只修改用户消息里“可修改文件”列出的文件，不要新建文件，不要修改测试。
2. 必须满足列出的全部规格条目；不得破坏回归测试覆盖的既有行为。
3. 只使用 Python 标准库；保持 Python 3.10+ 兼容。
4. 返回一个 JSON 对象，不要输出多余文字，格式：
   {"summary": "一句话说明改了什么",
    "files": [{"path": "相对 minimax/ 的路径", "content": "修改后的完整文件内容"}],
    "spec_coverage": ["SPEC-ORD-003#R1"],
    "notes": "可选说明"}
5. 不要输出 Markdown 代码块以外的解释；JSON 必须是合法 JSON（字符串内的换行用 \\n 转义）。"""


class MinimaxError(RuntimeError):
    """Raised when the MiniMax call fails or its answer cannot be used."""


@dataclass
class MinimaxResponse:
    ok: bool
    content: str
    request: dict[str, Any]
    response: dict[str, Any] | None
    error: str | None = None
    duration_s: float = 0.0
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "duration_s": round(self.duration_s, 3),
            "request": self.request,
            "response": self.response,
            "error": self.error,
        }


@dataclass
class ChangeSet:
    summary: str
    files: list[dict[str, str]]
    spec_coverage: list[str] = field(default_factory=list)
    notes: str = ""
    raw_text: str = ""

    @classmethod
    def from_content(cls, content: str) -> ChangeSet:
        payload = _extract_json(content)
        if payload is None:
            raise MinimaxError("MiniMax answer does not contain a JSON object")
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise MinimaxError("MiniMax answer has no files[]")
        normalised: list[dict[str, str]] = []
        for item in files:
            if not isinstance(item, dict) or "path" not in item or "content" not in item:
                raise MinimaxError("each file needs a path and content")
            normalised.append({"path": str(item["path"]), "content": str(item["content"])})
        return cls(
            summary=str(payload.get("summary") or ""),
            files=normalised,
            spec_coverage=[str(item) for item in payload.get("spec_coverage") or []],
            notes=str(payload.get("notes") or ""),
            raw_text=content,
        )


def _extract_json(text: str) -> dict[str, Any] | None:
    candidates: list[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    for fence in ("```json", "```"):
        if fence in stripped:
            for chunk in stripped.split(fence)[1:]:
                body = chunk.split("```", 1)[0].strip()
                if body:
                    candidates.append(body)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


class MinimaxClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2, max_tokens: int = 16000) -> MinimaxResponse:
        if not self.settings.minimax_api_key:
            raise MinimaxError(
                "MINIMAX_API_KEY is not set; export it or use --replay with a recorded response"
            )
        payload = {
            "model": self.settings.minimax_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.settings.minimax_base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.settings.minimax_api_key}")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.settings.minimax_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            raise MinimaxError(f"MiniMax HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MinimaxError(f"MiniMax endpoint unreachable: {exc.reason}") from exc
        duration = time.perf_counter() - started

        if body.get("base_resp", {}).get("status_code") not in (None, 0):
            raise MinimaxError(f"MiniMax error: {body['base_resp']}")
        choice = (body.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise MinimaxError(
                "MiniMax output was truncated (finish_reason=length) before the JSON answer; "
                "raise --max-tokens or shorten the context"
            )
        try:
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MinimaxError(f"unexpected MiniMax response shape: {json.dumps(body)[:500]}") from exc
        if not content:
            raise MinimaxError(
                f"MiniMax returned empty content (finish_reason={choice.get('finish_reason')!r})"
            )
        return MinimaxResponse(
            ok=True,
            content=content,
            request=payload,
            response=body,
            duration_s=duration,
            model=self.settings.minimax_model,
        )


def build_messages(settings: Settings, context: dict[str, Any], instruction: str = "") -> list[dict[str, str]]:
    files = sorted({item["source"]["path"] for item in context["code"]})
    sections = [context_for_prompt(context), "", "## 目标测试源码 (target tests, 只读)"]
    for item in context["tests"]["target"]:
        sections.append(f"### {item['node_id']}")
        sections.append(_read(settings, item["source"]["path"], item["source"]["start_line"], item["source"]["end_line"]))
    sections.append("")
    sections.append("## 可修改文件（请返回完整内容）")
    for path in files:
        sections.append(f"### {path}")
        sections.append("```python")
        sections.append((settings.workspace / path).read_text(encoding="utf-8"))
        sections.append("```")
    if instruction:
        sections.append("")
        sections.append("## 额外要求")
        sections.append(instruction)
    sections.append("")
    sections.append("请只返回约定的 JSON 对象。")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(sections)},
    ]


def _read(settings: Settings, path: str, start: int, end: int) -> str:
    lines = (settings.workspace / path).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[start - 1 : end])


def apply_changes(settings: Settings, changes: ChangeSet, allowed_paths: set[str]) -> dict[str, Any]:
    """Validate and write the files returned by the model."""

    written: list[dict[str, Any]] = []
    for item in changes.files:
        path = Path(item["path"].replace("\\", "/"))
        normalised = path.as_posix()
        if normalised.startswith("minimax/"):
            normalised = normalised[len("minimax/") :]
        if normalised not in allowed_paths:
            raise MinimaxError(f"refusing to write {normalised!r}: not in the selected file set")
        target = (settings.workspace / normalised).resolve()
        if settings.workspace.resolve() not in target.parents and target != settings.workspace.resolve():
            raise MinimaxError(f"refusing to write outside the workspace: {normalised}")
        new_content = item["content"]
        try:
            ast.parse(new_content)
        except SyntaxError as exc:
            raise MinimaxError(f"model returned invalid Python for {normalised}: {exc}") from exc
        before = target.read_text(encoding="utf-8")
        target.write_text(new_content, encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{normalised}",
                tofile=f"b/{normalised}",
            )
        )
        written.append({"path": normalised, "diff": diff, "changed": before != new_content})
    return {"files": written}


def save_transcript(settings: Settings, task_id: str, response: MinimaxResponse, changes: ChangeSet | None, applied: dict[str, Any] | None) -> Path:
    directory = settings.evidence_dir / "minimax" / task_id
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}.json"
    payload = {
        "task_id": task_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "response": response.as_dict(),
        "changes": None
        if changes is None
        else {
            "summary": changes.summary,
            "files": [item["path"] for item in changes.files],
            "spec_coverage": changes.spec_coverage,
            "notes": changes.notes,
        },
        "applied": applied,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_patch(settings: Settings, task_id: str, applied: dict[str, Any]) -> Path:
    directory = settings.evidence_dir / "changes"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task_id}.patch"
    path.write_text("".join(item["diff"] for item in applied["files"]), encoding="utf-8")
    return path


def load_replay(path: Path) -> ChangeSet:
    payload = json.loads(path.read_text(encoding="utf-8"))
    content = payload.get("content") or payload.get("changes", {}).get("raw_text")
    if content is None and "files" in payload:
        return ChangeSet(
            summary=payload.get("summary", "replayed change"),
            files=[{"path": f["path"], "content": f["content"]} for f in payload["files"]],
            spec_coverage=payload.get("spec_coverage") or [],
            notes=payload.get("notes", ""),
            raw_text="",
        )
    if content is None and payload.get("response", {}).get("response"):
        content = payload["response"]["response"]["choices"][0]["message"]["content"]
    if content is None:
        raise MinimaxError(f"{path}: no recorded MiniMax content found")
    return ChangeSet.from_content(content)
