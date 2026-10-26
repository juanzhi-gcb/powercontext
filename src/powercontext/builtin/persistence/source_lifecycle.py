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

"""Durable Source-lifecycle graph bindings and accepted event watermarks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.tables import (
    SOURCE_LIFECYCLE_EVENTS_TABLE,
    SOURCE_LIFECYCLE_NODES_TABLE,
)

LifecycleNodeKind = Literal["source", "memory", "topic"]
LifecyclePolicy = Literal["all", "any"]


class StoredLifecycleNode(BaseModel):
    """One registered graph node and its persisted availability."""

    model_config = ConfigDict(frozen=True)

    scope_id: str
    node_id: str
    kind: LifecycleNodeKind
    reference: dict[str, Any]
    revision: int | None
    parents: tuple[str, ...]
    policy: LifecyclePolicy | None
    available: bool


class StoredLifecycleEvent(BaseModel):
    """The latest accepted lifecycle event for one Source node."""

    model_config = ConfigDict(frozen=True)

    scope_id: str
    node_id: str
    sequence: int
    revision: int
    available: bool
    reason: str


class SourceLifecycleRepository:
    """Persist lifecycle bindings and event watermarks in caller transactions."""

    def __init__(self, database: AsyncDatabase) -> None:
        self.database = database

    async def load_node(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        /,
    ) -> StoredLifecycleNode | None:
        row = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE).where(
                    SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                    SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                )
            )
        ).mappings().one_or_none()
        return None if row is None else _decode_node(row)

    async def load_nodes(
        self,
        connection: AsyncConnection,
        scope_id: str,
        /,
    ) -> tuple[StoredLifecycleNode, ...]:
        rows = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE).where(
                    SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                )
            )
        ).mappings()
        return tuple(_decode_node(row) for row in rows)

    async def insert_node(
        self,
        connection: AsyncConnection,
        node: StoredLifecycleNode,
        /,
    ) -> None:
        await connection.execute(
            SOURCE_LIFECYCLE_NODES_TABLE.insert().values(
                scope_id=node.scope_id,
                node_id=node.node_id,
                kind=node.kind,
                reference=_dump_json(node.reference),
                revision=node.revision,
                parents=_dump_json(list(node.parents)),
                policy=node.policy,
                available=node.available,
            )
        )

    async def load_event(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        /,
    ) -> StoredLifecycleEvent | None:
        row = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_EVENTS_TABLE).where(
                    SOURCE_LIFECYCLE_EVENTS_TABLE.c.scope_id == scope_id,
                    SOURCE_LIFECYCLE_EVENTS_TABLE.c.node_id == node_id,
                )
            )
        ).mappings().one_or_none()
        return None if row is None else _decode_event(row)

    async def write_event(
        self,
        connection: AsyncConnection,
        event: StoredLifecycleEvent,
        /,
    ) -> None:
        await connection.execute(
            SOURCE_LIFECYCLE_EVENTS_TABLE.delete().where(
                SOURCE_LIFECYCLE_EVENTS_TABLE.c.scope_id == event.scope_id,
                SOURCE_LIFECYCLE_EVENTS_TABLE.c.node_id == event.node_id,
            )
        )
        await connection.execute(
            SOURCE_LIFECYCLE_EVENTS_TABLE.insert().values(
                scope_id=event.scope_id,
                node_id=event.node_id,
                sequence=event.sequence,
                revision=event.revision,
                available=event.available,
                reason=event.reason,
            )
        )

    async def set_availability(
        self,
        connection: AsyncConnection,
        scope_id: str,
        availability: Mapping[str, bool],
        /,
    ) -> None:
        for node_id, available in availability.items():
            await connection.execute(
                update(SOURCE_LIFECYCLE_NODES_TABLE)
                .where(
                    SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                    SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                )
                .values(available=available)
            )

    async def inactive_topic_artifact_ids(
        self,
        connection: AsyncConnection,
        scope_id: str,
        /,
    ) -> frozenset[str]:
        """Return explicitly unavailable registered Topic artifact ids.

        Only Topics that took part in lifecycle registration are excluded; this
        is a blocklist, never an allowlist, so ordinary Topics stay visible.
        """

        rows = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE.c.reference).where(
                    SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                    SOURCE_LIFECYCLE_NODES_TABLE.c.kind == "topic",
                    SOURCE_LIFECYCLE_NODES_TABLE.c.available.is_(False),
                )
            )
        ).scalars()
        artifact_ids: set[str] = set()
        for raw in rows:
            data = json.loads(raw)
            artifact_id = data.get("artifact_id")
            if isinstance(artifact_id, str):
                artifact_ids.add(artifact_id)
        return frozenset(artifact_ids)


def _decode_node(row: Mapping[str, Any]) -> StoredLifecycleNode:
    return StoredLifecycleNode(
        scope_id=row["scope_id"],
        node_id=row["node_id"],
        kind=row["kind"],
        reference=json.loads(row["reference"]),
        revision=None if row["revision"] is None else int(row["revision"]),
        parents=tuple(json.loads(row["parents"])),
        policy=row["policy"],
        available=bool(row["available"]),
    )


def _decode_event(row: Mapping[str, Any]) -> StoredLifecycleEvent:
    return StoredLifecycleEvent(
        scope_id=row["scope_id"],
        node_id=row["node_id"],
        sequence=int(row["sequence"]),
        revision=int(row["revision"]),
        available=bool(row["available"]),
        reason=row["reason"],
    )


def _dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)