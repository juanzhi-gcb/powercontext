from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .comparator import Comparator
from .context import (
    PowerContextAdapter,
    PowerContextUnavailable,
    artifact_ref,
    artifact_text,
)
from .embeddings import Embedder
from .evaluation import evaluate
from .models import (
    ArchiveCard,
    ArchiveImport,
    AttemptCreate,
    EvaluationRunCreate,
    EvidenceInput,
    ReplayCreate,
    ResearchSourceImport,
    SecretaryReviewCreate,
)
from .secretary import build_proposals, now_iso, secretary_context
from .store import SeekDBStore


class CutoffViolationError(ValueError):
    pass


def split_source(content: str, limit: int = 8000) -> list[str]:
    remaining = content.strip()
    chunks = []
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    if len(chunks) > 1 and len(chunks[-1]) < 10:
        chunks[-2] = f"{chunks[-2]}\n\n{chunks[-1]}"
        chunks.pop()
    return chunks


class ResearchService:
    def __init__(
        self,
        store: SeekDBStore,
        embedder: Embedder,
        comparator: Comparator,
        context: PowerContextAdapter,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.comparator = comparator
        self.context = context

    def embedding_text(self, attempt: AttemptCreate | dict[str, Any]) -> str:
        if isinstance(attempt, AttemptCreate):
            return " ".join(
                [attempt.idea, attempt.mechanism, attempt.failure_condition, *attempt.assumptions]
            )
        return " ".join(
            [
                attempt["idea"],
                attempt["mechanism"],
                attempt["failure_condition"],
                *attempt.get("assumptions", []),
            ]
        )

    def create_attempt(self, attempt: AttemptCreate) -> dict[str, Any]:
        return self.store.create_attempt(attempt, self.embedder.embed(self.embedding_text(attempt)))

    def search_history(self, query: str) -> dict[str, Any]:
        cutoff = datetime.now(UTC)
        search_attempt = {
            "id": "read-only-history-search",
            "idea": query,
            "mechanism": query,
            "failure_condition": "",
            "task": "research",
            "domain": "research",
        }
        embedding = self.embedder.embed(query)
        candidates = self.store.hybrid_retrieve(search_attempt, embedding, cutoff, limit=6)
        evidence = self.store.evidence_for_attempts(
            [candidate["id"] for candidate in candidates], cutoff
        )
        candidates = [candidate for candidate in candidates if evidence.get(candidate["id"])][:3]
        return {
            "query": query,
            "cutoff": cutoff.isoformat(),
            "results": [
                {
                    "attempt_id": candidate["id"],
                    "title": candidate["title"],
                    "task": candidate["task"],
                    "domain": candidate["domain"],
                    "historical_decision": candidate.get("historical_decision"),
                    "available_at": candidate["available_at"],
                    "mechanism": candidate["mechanism"],
                    "differentiator": candidate.get("differentiator", ""),
                    "vector_distance": candidate.get("vector_distance"),
                    "fts_score": candidate.get("fts_score"),
                    "fused_score": candidate["fused_score"],
                    "evidence": evidence.get(candidate["id"], []),
                }
                for candidate in candidates
            ],
            "retrieval": "seekdb-vector-fts-rrf-v1",
        }

    def import_archive(self, archive: ArchiveImport) -> list[dict[str, Any]]:
        existing_titles = {item["title"] for item in self.store.list_attempts()}
        imported = []
        for card in archive.cards:
            if card.attempt.title in existing_titles:
                continue
            imported.append(
                self.store.import_card(card, self.embedder.embed(self.embedding_text(card.attempt)))
            )
        return imported

    def import_sources(self, source_import: ResearchSourceImport) -> dict[str, Any]:
        imported = []
        skipped = 0
        for source in source_import.sources:
            chunks = split_source(source.content)
            for index, chunk in enumerate(chunks, start=1):
                digest = hashlib.sha256(f"{source.locator}\0{chunk}".encode()).hexdigest()[:24]
                attempt_id = f"source-{digest}"
                if self.store.has_attempt(attempt_id):
                    skipped += 1
                    continue
                title = (
                    source.title
                    if len(chunks) == 1
                    else f"{source.title[:260]} · {index}/{len(chunks)}"
                )
                locator = (
                    source.locator
                    if len(chunks) == 1
                    else f"{source.locator}#part-{index}-of-{len(chunks)}"
                )
                card = ArchiveCard(
                    attempt=AttemptCreate(
                        title=title,
                        idea=chunk,
                        mechanism=chunk,
                        task=source.task,
                        domain=source.domain,
                        failure_condition="External source record; no failure condition declared.",
                        available_at=source.published_at,
                    ),
                    evidence=[
                        EvidenceInput(
                            id=f"source-evidence-{digest}",
                            source_type=source.source_type,
                            title=title,
                            locator=locator,
                            excerpt=chunk,
                            stance="supports",
                            published_at=source.published_at,
                        )
                    ],
                )
                imported.append(
                    self.store.import_card(
                        card,
                        self.embedder.embed(self.embedding_text(card.attempt)),
                        attempt_id=attempt_id,
                    )
                )
        return {
            "documents": len(source_import.sources),
            "imported": len(imported),
            "skipped": skipped,
            "attempts": imported,
        }

    def run_secretary(self) -> dict[str, Any]:
        documents = self.store.list_source_documents()
        workspace, _ = self._load_secretary_workspace()
        reviews = workspace.get("reviews", {}) if isinstance(workspace, dict) else {}
        previous_source_ids = set(workspace.get("known_source_ids", []))
        proposals, new_source_ids = build_proposals(documents, reviews, previous_source_ids)
        generated_at = now_iso()
        run_id = f"secretary-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        workspace = {
            "schema": "nullpath.secretary-workspace.v1",
            "run_id": run_id,
            "generated_at": generated_at,
            "source_count": len(documents),
            "known_source_ids": [document["attempt_id"] for document in documents],
            "new_source_ids": new_source_ids,
            "proposals": proposals,
            "reviews": reviews,
        }
        workspace["context_ref"] = self._save_secretary_context(proposals, generated_at)
        record = self.context.save_state(
            "secretary_workspace", json.dumps(workspace, ensure_ascii=False, separators=(",", ":"))
        )
        return self._secretary_report(
            workspace, {**artifact_ref(record), "kind": "secretary_workspace"}
        )

    def get_secretary(self) -> dict[str, Any]:
        workspace, ref = self._load_secretary_workspace()
        if not workspace:
            return {
                "status": "not_run",
                "run_id": None,
                "generated_at": None,
                "source_count": 0,
                "new_source_ids": [],
                "new_source_count": 0,
                "accepted_count": 0,
                "proposals": [],
                "workspace": None,
                "context": None,
            }
        return self._secretary_report(workspace, ref)

    def review_secretary(self, review: SecretaryReviewCreate) -> dict[str, Any]:
        workspace, _ = self._load_secretary_workspace()
        proposals = workspace.get("proposals", []) if isinstance(workspace, dict) else []
        proposal = next((item for item in proposals if item["id"] == review.proposal_id), None)
        if proposal is None:
            raise KeyError(f"Secretary proposal not found: {review.proposal_id}")
        reviewed_at = now_iso()
        reviews = workspace.setdefault("reviews", {})
        reviews[review.proposal_id] = {
            "status": review.status,
            "note": review.note,
            "reviewed_at": reviewed_at,
        }
        proposal["status"] = review.status
        proposal["review_note"] = review.note
        proposal["reviewed_at"] = reviewed_at
        workspace["context_ref"] = self._save_secretary_context(proposals, reviewed_at)
        record = self.context.save_state(
            "secretary_workspace", json.dumps(workspace, ensure_ascii=False, separators=(",", ":"))
        )
        return self._secretary_report(
            workspace, {**artifact_ref(record), "kind": "secretary_workspace"}
        )

    def _load_secretary_workspace(self) -> tuple[dict[str, Any], dict[str, Any] | None]:
        for record in self.context.list_kind("secretary_workspace"):
            try:
                workspace = json.loads(artifact_text(record))
            except json.JSONDecodeError:
                continue
            if isinstance(workspace, dict):
                return workspace, {**artifact_ref(record), "kind": "secretary_workspace"}
        return {}, None

    def _save_secretary_context(
        self, proposals: list[dict[str, Any]], generated_at: str
    ) -> dict[str, Any] | None:
        accepted = any(proposal["status"] == "accepted" for proposal in proposals)
        existing = self.context.list_kind("secretary_context")
        if not accepted and not existing:
            return None
        text = secretary_context(proposals, generated_at)
        incoming = json.loads(text)
        incoming.pop("updated_at", None)
        for record in existing:
            current = json.loads(artifact_text(record) or "{}")
            current.pop("updated_at", None)
            if current == incoming:
                return {**artifact_ref(record), "kind": "secretary_context"}
        record = self.context.save_state("secretary_context", text)
        return {**artifact_ref(record), "kind": "secretary_context"}

    @staticmethod
    def _secretary_report(workspace: dict[str, Any], ref: dict[str, Any] | None) -> dict[str, Any]:
        proposals = workspace.get("proposals", [])
        new_source_ids = workspace.get("new_source_ids", [])
        return {
            "status": "ready",
            "run_id": workspace.get("run_id"),
            "generated_at": workspace.get("generated_at"),
            "source_count": workspace.get("source_count", 0),
            "new_source_ids": new_source_ids,
            "new_source_count": len(new_source_ids),
            "accepted_count": sum(1 for item in proposals if item.get("status") == "accepted"),
            "proposals": proposals,
            "workspace": ref,
            "context": workspace.get("context_ref"),
        }

    def run_evaluation(
        self,
        request: EvaluationRunCreate,
        *,
        replay: ReplayCreate | None = None,
        original_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt = self.store.get_attempt(request.attempt_id)
        if datetime.fromisoformat(attempt["available_at"]) > request.cutoff:
            raise CutoffViolationError("Candidate attempt is not available at the requested cutoff")
        embedding = self.embedder.embed(self.embedding_text(attempt))
        context_entries: list[dict[str, Any]] = []
        context_warning = None
        if replay and original_run:
            context_refs = original_run.get("context_refs", [])
            if context_refs:
                try:
                    context_entries = self.context.load_exact(context_refs)
                except PowerContextUnavailable as error:
                    context_warning = str(error)
        elif request.use_context and self.context.configured:
            try:
                context_entries = self.context.load_active()
            except PowerContextUnavailable as error:
                context_warning = str(error)
        context_refs = self.context.references(context_entries)

        candidates = self.store.hybrid_retrieve(attempt, embedding, request.cutoff)
        evidence = self.store.evidence_for_attempts(
            [candidate["id"] for candidate in candidates], request.cutoff
        )
        report = evaluate(
            attempt,
            request.cutoff,
            candidates,
            evidence,
            self.comparator,
            self.comparator.version,
            self.embedder.version,
            context_entries,
            context_refs,
            context_warning,
        )
        snapshot_hash, snapshot_counts = self.store.snapshot_hash(request.cutoff)
        report["snapshot"] = {"hash": snapshot_hash, **snapshot_counts}
        report["snapshot_hash"] = snapshot_hash
        if replay and original_run:
            recalled = set(report["evidence_ids"])
            required = set(replay.required_evidence_ids)
            forbidden = set(replay.forbidden_evidence_ids)
            future_evidence = [
                item["id"]
                for comparison in report["comparisons"]
                for item in comparison["evidence"]
                if item["published_at"] > report["cutoff"]
            ]
            assertions = {
                "decision": report["machine_decision"] == replay.expected_decision.value,
                "required_evidence": required <= recalled,
                "forbidden_evidence": not (forbidden & recalled),
                "cutoff_integrity": not future_evidence,
                "snapshot_integrity": snapshot_hash == original_run["snapshot_hash"],
                "version_integrity": report["versions"] == original_run["versions"],
                "context_integrity": context_refs == original_run.get("context_refs", []),
            }
            report["replay_of"] = original_run["id"]
            report["regression"] = {
                "passed": all(assertions.values()),
                "assertions": assertions,
                "expected_decision": replay.expected_decision.value,
                "actual_decision": report["machine_decision"],
                "required_evidence_ids": replay.required_evidence_ids,
                "forbidden_evidence_ids": replay.forbidden_evidence_ids,
                "leaked_evidence_ids": future_evidence,
                "note": "Input evidence is cutoff-safe; model training knowledge is not claimed to be time-bounded.",
            }
        return self.store.save_evaluation(
            request.attempt_id,
            request,
            report,
            snapshot_hash=snapshot_hash,
            context_refs=context_refs,
            replay_of=original_run["id"] if original_run else None,
        )

    def replay(self, replay: ReplayCreate) -> dict[str, Any]:
        original = self.store.get_run(replay.source_run_id)
        request = EvaluationRunCreate(
            attempt_id=original["attempt_id"], cutoff=original["cutoff"], use_context=False
        )
        return self.run_evaluation(request, replay=replay, original_run=original)
