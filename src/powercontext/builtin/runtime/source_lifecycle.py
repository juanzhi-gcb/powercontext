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

"""Dependency-driven Source lifecycle over a per-Scope evidence DAG.

A Scope registers Source, Memory and Topic Memory nodes together with the
parents that support them.  Withdrawing or restoring a Source propagates
through ``all``/``any`` policies to every descendant; native Memory entries are
deactivated/reactivated and Topic Memory visibility follows the graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.source_lifecycle import (
    LifecycleNodeKind,
    LifecyclePolicy,
    SourceLifecycleRepository,
    StoredLifecycleEvent,
    StoredLifecycleNode,
)
from powercontext.builtin.sources import validate_scope_id
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import BuiltinRuntime

_PURPOSES = frozenset({"generation", "audit"})
_POLICIES = frozenset({"all", "any"})


class SourceLifecycleError(ValueError):
    """A rejected lifecycle contract operation.

    Construction-time shape errors surface as pydantic ``ValidationError``;
    every runtime contract violation (unknown node, stale revision, conflicting
    replay, invalid DAG edge, ...) raises this instead.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


class SourceLifecycleEvent(BaseModel):
    """One immutable availability transition for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str
    revision: int
    sequence: int
    available: bool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def _require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty non-blank string")
        return value

    @field_validator("revision", "sequence")
    @classmethod
    def _require_positive_int(cls, value: int) -> int:
        if isinstance(value, bool) or value < 1:
            raise ValueError("must be a positive integer")
        return value


class SourceLifecycleApplication:
    """Select a Scope-bound Source lifecycle service."""

    def __init__(
        self,
        runtime: BuiltinRuntime,
        repository: SourceLifecycleRepository | None = None,
    ) -> None:
        self._runtime = runtime
        self._repository = repository

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycleApplication:
        return ScopedSourceLifecycleApplication(self._runtime, self._repository, scope_id)


class ScopedSourceLifecycleApplication:
    """Register one Scope's evidence DAG and propagate Source transitions."""

    def __init__(
        self,
        runtime: BuiltinRuntime,
        repository: SourceLifecycleRepository | None,
        scope_id: str,
    ) -> None:
        self._runtime = runtime
        self._repository = repository
        self.scope_id = validate_scope_id(scope_id)

    # Registration -----------------------------------------------------------------

    async def register_source(
        self,
        node_id: str,
        source_ref: SourceRef,
        *,
        revision: int,
    ) -> None:
        node_id = _validate_node_id(node_id)
        revision = _validate_positive_int("revision", revision)
        if not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError("reference", "source_ref must be a SourceRef")
        await self._register(
            node_id=node_id,
            kind="source",
            reference=source_ref,
            revision=revision,
            parents=(),
            policy=None,
            available=True,
        )

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        node_id = _validate_node_id(node_id)
        validated_parents = _validate_parents(node_id, parents)
        validated_policy = _validate_policy(policy)
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("reference", "citation must be a MemoryCitation")
        await self._register(
            node_id=node_id,
            kind="memory",
            reference=citation,
            revision=None,
            parents=validated_parents,
            policy=validated_policy,
            available=None,
        )

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Literal["all", "any"],
    ) -> None:
        node_id = _validate_node_id(node_id)
        validated_parents = _validate_parents(node_id, parents)
        validated_policy = _validate_policy(policy)
        if not isinstance(artifact_ref, ArtifactRef):
            raise SourceLifecycleError("reference", "artifact_ref must be an ArtifactRef")
        await self._register(
            node_id=node_id,
            kind="topic",
            reference=artifact_ref,
            revision=None,
            parents=validated_parents,
            policy=validated_policy,
            available=None,
        )

    # Event application ------------------------------------------------------------

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:
        """Apply one Source event and return every available node id, sorted.

        Native Memory state is written before the event watermark and the
        propagated node states are committed, so an interrupted attempt leaves
        the event unacknowledged and a retry finishes the propagation.
        """

        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("event", "must be a SourceLifecycleEvent")
        repository = self._require_repository()
        async with repository.database.transaction() as connection:
            nodes = await repository.load_nodes(connection, self.scope_id)
            by_id = {node.node_id: node for node in nodes}
            source = by_id.get(event.node_id)
            if source is None:
                raise SourceLifecycleError("unknown-node", event.node_id)
            if source.kind != "source":
                raise SourceLifecycleError("not-source", event.node_id)
            if source.revision is None or source.revision != event.revision:
                raise SourceLifecycleError("revision", event.node_id)
            previous = await repository.load_event(connection, self.scope_id, event.node_id)
            if previous is not None:
                if event.sequence < previous.sequence:
                    raise SourceLifecycleError("sequence", event.node_id)
                if event.sequence == previous.sequence:
                    if (event.revision, event.available, event.reason) != (
                        previous.revision,
                        previous.available,
                        previous.reason,
                    ):
                        raise SourceLifecycleError("event-conflict", event.node_id)
                    return _active_ids(nodes)
            target = _propagate(by_id, event)
        changed = {
            node_id: available for node_id, available in target.items() if by_id[node_id].available != available
        }
        for node_id in sorted(changed):
            node = by_id[node_id]
            if node.kind != "memory":
                continue
            citation = _decode_reference(node)
            if not isinstance(citation, MemoryCitation):
                raise SourceLifecycleError("reference", node_id)
            await self._memory()._apply_lifecycle_state(
                citation,
                active=changed[node_id],
                reason=event.reason,
            )
        async with repository.database.transaction() as connection:
            current = await repository.load_event(connection, self.scope_id, event.node_id)
            if current != previous:
                raise SourceLifecycleError("conflict", event.node_id)
            await repository.set_availability(connection, self.scope_id, changed)
            await repository.write_event(
                connection,
                StoredLifecycleEvent(
                    scope_id=self.scope_id,
                    node_id=event.node_id,
                    sequence=event.sequence,
                    revision=event.revision,
                    available=event.available,
                    reason=event.reason,
                ),
            )
        return sorted(node_id for node_id, available in target.items() if available)

    # Resolution -------------------------------------------------------------------

    async def resolve(self, node_id: str, *, purpose: Literal["generation", "audit"]) -> Any:
        """Return the original reference registered for one node."""

        if purpose not in _PURPOSES:
            raise SourceLifecycleError("purpose", str(purpose))
        node_id = _validate_node_id(node_id)
        repository = self._require_repository()
        async with repository.database.transaction() as connection:
            node = await repository.load_node(connection, self.scope_id, node_id)
        if node is None:
            raise SourceLifecycleError("unknown-node", node_id)
        if purpose == "generation" and not node.available:
            raise SourceLifecycleError("unavailable", node_id)
        return _decode_reference(node)

    # Internals --------------------------------------------------------------------

    async def _register(
        self,
        *,
        node_id: str,
        kind: LifecycleNodeKind,
        reference: SourceRef | MemoryCitation | ArtifactRef,
        revision: int | None,
        parents: tuple[str, ...],
        policy: LifecyclePolicy | None,
        available: bool | None,
    ) -> None:
        repository = self._require_repository()
        async with repository.database.transaction() as connection:
            existing = await repository.load_node(connection, self.scope_id, node_id)
            nodes = await repository.load_nodes(connection, self.scope_id)
        payload = reference.model_dump(mode="json")
        if existing is not None:
            same = _same_binding(
                existing,
                kind=kind,
                payload=payload,
                revision=revision,
                parents=parents,
                policy=policy,
            )
            if not same:
                raise SourceLifecycleError("conflict", node_id)
            if kind == "memory":
                previous_reference = _decode_reference(existing)
                if not isinstance(previous_reference, MemoryCitation):
                    raise SourceLifecycleError("reference", node_id)
                await self._memory()._apply_lifecycle_state(
                    previous_reference,
                    active=existing.available,
                )
            return
        if available is None:
            by_id = {node.node_id: node for node in nodes}
            available = _evaluate_new_node(node_id, parents, policy, by_id)
        await self._validate_reference(kind, reference)
        stored = StoredLifecycleNode(
            scope_id=self.scope_id,
            node_id=node_id,
            kind=kind,
            reference=payload,
            revision=revision,
            parents=parents,
            policy=policy,
            available=available,
        )
        async with repository.database.transaction() as connection:
            if await repository.load_node(connection, self.scope_id, node_id) is not None:
                raise SourceLifecycleError("conflict", node_id)
            await repository.insert_node(connection, stored)
        if kind == "memory" and isinstance(reference, MemoryCitation):
            await self._memory()._apply_lifecycle_state(reference, active=available)

    async def _validate_reference(
        self,
        kind: LifecycleNodeKind,
        reference: SourceRef | MemoryCitation | ArtifactRef,
    ) -> None:
        """Reject a reference that cannot be read back in this Scope."""

        try:
            if kind == "source" and isinstance(reference, SourceRef):
                await self._runtime.records.for_scope(self.scope_id).get_source(
                    reference.source_type,
                    reference.source_id,
                )
            elif kind == "memory" and isinstance(reference, MemoryCitation):
                from powercontext.builtin.runtime.application import GetMemoryEntryRequest

                await self._runtime.memory.for_scope(self.scope_id).get(
                    GetMemoryEntryRequest(citation=reference)
                )
            elif kind == "topic" and isinstance(reference, ArtifactRef):
                await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                    reference.family,
                    reference.artifact_id,
                    reference.revision,
                )
        except SourceLifecycleError:
            raise
        except Exception as error:  # noqa: BLE001 - normalize every unreadable reference
            raise SourceLifecycleError("reference", kind) from error

    def _memory(self):
        return self._runtime.memory.for_scope(self.scope_id)

    def _require_repository(self) -> SourceLifecycleRepository:
        if self._repository is None:
            raise SourceLifecycleError("unavailable", "Source lifecycle persistence is not configured")
        return self._repository


def _active_ids(nodes: tuple[StoredLifecycleNode, ...]) -> list[str]:
    return sorted(node.node_id for node in nodes if node.available)


def _validate_node_id(node_id: str) -> str:
    if not isinstance(node_id, str) or not node_id.strip():
        raise SourceLifecycleError("node-id", "must be a non-empty non-blank string")
    return node_id


def _validate_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SourceLifecycleError(name, "must be a positive integer")
    return value


def _validate_parents(node_id: str, parents: object) -> tuple[str, ...]:
    if isinstance(parents, (str, bytes)) or not isinstance(parents, (tuple, list)):
        raise SourceLifecycleError("parents", "must be a tuple of node ids")
    validated: list[str] = []
    for parent in parents:
        if not isinstance(parent, str) or not parent.strip():
            raise SourceLifecycleError("parents", "parent ids must be non-empty non-blank strings")
        if parent == node_id:
            raise SourceLifecycleError("cycle", node_id)
        validated.append(parent)
    if not validated:
        raise SourceLifecycleError("parents", "at least one parent is required")
    if len(set(validated)) != len(validated):
        raise SourceLifecycleError("parents", "parent ids must not repeat")
    return tuple(validated)


def _validate_policy(policy: object) -> LifecyclePolicy:
    if not isinstance(policy, str) or policy not in _POLICIES:
        raise SourceLifecycleError("policy", str(policy))
    return cast(LifecyclePolicy, policy)


def _same_binding(
    node: StoredLifecycleNode,
    *,
    kind: LifecycleNodeKind,
    payload: Mapping[str, Any],
    revision: int | None,
    parents: tuple[str, ...],
    policy: LifecyclePolicy | None,
) -> bool:
    return (
        node.kind == kind
        and node.reference == payload
        and node.revision == revision
        and frozenset(node.parents) == frozenset(parents)
        and node.policy == policy
    )


def _evaluate_new_node(
    node_id: str,
    parents: tuple[str, ...],
    policy: LifecyclePolicy | None,
    by_id: Mapping[str, StoredLifecycleNode],
) -> bool:
    parent_nodes: list[StoredLifecycleNode] = []
    for parent in parents:
        node = by_id.get(parent)
        if node is None:
            raise SourceLifecycleError("unknown-parent", f"{node_id}->{parent}")
        parent_nodes.append(node)
    if policy == "all":
        return all(node.available for node in parent_nodes)
    if policy == "any":
        return any(node.available for node in parent_nodes)
    raise SourceLifecycleError("policy", node_id)


def _propagate(by_id: Mapping[str, StoredLifecycleNode], event: SourceLifecycleEvent) -> dict[str, bool]:
    """Recompute every node's availability in memory from the persisted graph."""

    state: dict[str, bool] = {}
    visiting: set[str] = set()

    def evaluate(node_id: str) -> bool:
        cached = state.get(node_id)
        if cached is not None:
            return cached
        node = by_id.get(node_id)
        if node is None:
            raise SourceLifecycleError("unknown-parent", node_id)
        if node_id in visiting:
            raise SourceLifecycleError("cycle", node_id)
        visiting.add(node_id)
        try:
            if node.kind == "source":
                value = event.available if node_id == event.node_id else node.available
            else:
                supports = [evaluate(parent) for parent in node.parents]
                if node.policy == "all":
                    value = all(supports)
                elif node.policy == "any":
                    value = any(supports)
                else:
                    raise SourceLifecycleError("policy", node_id)
        finally:
            visiting.discard(node_id)
        state[node_id] = value
        return value

    for node_id in by_id:
        evaluate(node_id)
    return state


def _decode_reference(node: StoredLifecycleNode) -> SourceRef | MemoryCitation | ArtifactRef:
    if node.kind == "source":
        return SourceRef.model_validate(node.reference)
    if node.kind == "memory":
        return MemoryCitation.model_validate(node.reference)
    return ArtifactRef.model_validate(node.reference)