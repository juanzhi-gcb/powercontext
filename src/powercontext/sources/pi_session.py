# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capture the visible events on one Pi session branch as immutable Sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.connectors import (
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
)
from powercontext.sources.definitions import SourceDefinition
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
PI_SESSION_CONNECTOR_VERSION = "1"
PI_EVENT_DEFINITION_VERSION = "1"

_CHECKPOINT_SCHEMA = "powercontext.pi-session-checkpoint.v1"
_SUPPORTED_VERSION = 3
_SOURCE_ID_PREFIX = "pi"


class PiSessionInput(BaseModel):
    """One Pi v3 JSONL archive and the leaf whose ancestry defines the branch."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible event on the selected branch, with its complete source record."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: JsonValue


class PiEventSource(Source):
    """A captured event whose identity is its session and event identifier."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: JsonValue

    @property
    def source_id(self) -> str:
        return self.name


def parse_pi_session(value: PiSessionInput, /) -> tuple[PiEventInput, ...]:
    """Return the visible ancestors of one leaf ordered from root to leaf."""

    try:
        text = value.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Pi session content must be valid UTF-8") from error  # noqa: TRY003

    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("Pi session content must be JSONL") from error  # noqa: TRY003
        if not isinstance(record, dict):
            raise ValueError("every Pi session record must be a JSON object")  # noqa: TRY003
        records.append(record)
    if not records:
        raise ValueError("Pi session content must not be empty")  # noqa: TRY003

    session_id = _session_id(records[0])
    nodes: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records[1:]:
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("every Pi event must have a non-empty id")  # noqa: TRY003
        if event_id in nodes:
            raise ValueError("Pi event ids must be unique")  # noqa: TRY003
        parent_id = record.get("parentId")
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id not in nodes):
            raise ValueError("Pi event parents must be empty or point to an earlier event")  # noqa: TRY003
        nodes[event_id] = record
        order.append(event_id)

    leaf_id = value.leaf_id if value.leaf_id is not None else (order[-1] if order else None)
    if leaf_id is None or leaf_id not in nodes:
        raise ValueError("the selected Pi leaf must name an existing event")  # noqa: TRY003

    events: list[PiEventInput] = []
    for event_id in _ancestry(nodes, leaf_id):
        event = _visible_event(session_id=session_id, event_id=event_id, record=nodes[event_id])
        if event is not None:
            events.append(event)
    return tuple(events)


class PiSessionConnector:
    """Import only the visible events of one branch that are not yet checkpointed."""

    name = PI_SESSION_CONNECTOR_NAME
    version = PI_SESSION_CONNECTOR_VERSION
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        events = parse_pi_session(PiSessionInput(content=self._path.read_bytes(), leaf_id=self._leaf_id))
        imported = _load_checkpoint(session.checkpoint)
        for event in events:
            digest = _record_digest(event.record)
            known = imported.get(event.event_id)
            if known is not None:
                if known != digest:
                    raise ValueError(  # noqa: TRY003
                        f"Pi event {event.event_id!r} changed after it was captured"
                    )
                continue
            outcome = await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            if outcome.status.value == "accepted":
                imported[event.event_id] = digest
        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE,
            checkpoint={"schema": _CHECKPOINT_SCHEMA, "events": imported},
        )


class PiEventSourceAdapter:
    """Resolve and read one captured Pi event."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        return PiEventSource(
            name=pi_event_source_id(value.session_id, value.event_id),
            definition_version=PI_EVENT_DEFINITION_VERSION,
            materialization=SourceMaterialization.CAPTURED,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


class PiEventTextEvidenceProjection:
    """Expose one captured event as the standard text-evidence projection."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.name,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


def pi_event_source_id(session_id: str, event_id: str, /) -> str:
    """Build the stable identity of one captured event."""

    for field, value in (("session_id", session_id), ("event_id", event_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")  # noqa: TRY003
    source_id = f"{_SOURCE_ID_PREFIX}:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("Pi event source identity exceeds the supported length")  # noqa: TRY003
    return source_id


PI_EVENT_SOURCE_DEFINITION: SourceDefinition[PiEventInput, PiEventSource, PiEventInput] = AdapterSourceDefinition(
    PiEventSourceAdapter(),
    version=PI_EVENT_DEFINITION_VERSION,
    projections=(PiEventTextEvidenceProjection(),),
)


def _session_id(header: dict[str, Any]) -> str:
    if header.get("type") != "session":
        raise ValueError("the first Pi record must be a session header")  # noqa: TRY003
    if header.get("version") != _SUPPORTED_VERSION:
        raise ValueError("only Pi session version 3 is supported")  # noqa: TRY003
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("the Pi session header must carry a non-empty id")  # noqa: TRY003
    return session_id


def _ancestry(nodes: dict[str, dict[str, Any]], leaf_id: str) -> list[str]:
    chain: list[str] = []
    cursor: str | None = leaf_id
    while cursor is not None:
        chain.append(cursor)
        cursor = nodes[cursor].get("parentId")
    chain.reverse()
    return chain


def _visible_event(*, session_id: str, event_id: str, record: dict[str, Any]) -> PiEventInput | None:
    event_type = record.get("type")
    if not isinstance(event_type, str):
        return None
    if event_type == "message":
        role, body = _message_text(record.get("message"))
    elif event_type in {"compaction", "branch_summary"}:
        role = event_type
        summary = record.get("summary")
        body = summary if isinstance(summary, str) else ""
    elif event_type == "custom_message":
        role = "custom"
        body = _blocks_text(record.get("content"))
    else:
        return None
    if not body.strip():
        return None
    return PiEventInput(
        session_id=session_id,
        event_id=event_id,
        parent_id=record.get("parentId"),
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def _message_text(message: object) -> tuple[str, str]:
    if not isinstance(message, dict):
        return "", ""
    role = message.get("role")
    role = role if isinstance(role, str) and role else "message"
    if role == "toolResult":
        tool_name = message.get("toolName")
        tool_name = tool_name if isinstance(tool_name, str) and tool_name else "unknown"
        call_id = message.get("toolCallId")
        call_id = call_id if isinstance(call_id, str) else ""
        return role, f"[tool_result {tool_name} {call_id}] {_blocks_text(message.get('content'))}"
    if role == "bashExecution":
        command = message.get("command")
        command = command if isinstance(command, str) else ""
        output = message.get("output")
        output = output if isinstance(output, str) else ""
        return role, f"$ {command}\n{output}"
    return role, _blocks_text(message.get("content"))


def _blocks_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif kind == "toolCall":
            name = block.get("name")
            name = name if isinstance(name, str) else ""
            call_id = block.get("id")
            call_id = call_id if isinstance(call_id, str) else ""
            arguments = block.get("arguments")
            parts.append(f"[tool_call {name} {call_id}] {_compact_json(arguments)}")
    return "\n".join(parts)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_digest(record: JsonValue) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_checkpoint(checkpoint: JsonValue | None) -> dict[str, str]:
    if checkpoint is None:
        return {}
    if not isinstance(checkpoint, dict) or checkpoint.get("schema") != _CHECKPOINT_SCHEMA:
        raise ValueError("unrecognised Pi session checkpoint")  # noqa: TRY003
    events = checkpoint.get("events")
    if not isinstance(events, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in events.items()
    ):
        raise ValueError("malformed Pi session checkpoint events")  # noqa: TRY003
    return dict(events)


__all__ = [
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_SESSION_CONNECTOR_NAME",
    "PI_SESSION_CONNECTOR_VERSION",
    "PiEventInput",
    "PiEventSource",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
    "pi_event_source_id",
]