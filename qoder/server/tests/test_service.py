import json
from datetime import UTC, datetime

import pytest

from nullpath.comparator import DeterministicComparator
from nullpath.config import Settings
from nullpath.context import PowerContextAdapter
from nullpath.embeddings import HashingEmbedder
from nullpath.models import (
    EvaluationRunCreate,
    ReplayCreate,
    ResearchSourceImport,
    SecretaryReviewCreate,
)
from nullpath.service import CutoffViolationError, ResearchService


class FakeStore:
    def __init__(self):
        self.snapshot = ("snapshot-a", {"attempts": 1, "evidence": 0})
        self.runs = {}
        self.imported = []
        self.existing_attempt_ids = set()
        self.source_documents = []
        self.attempt = {
            "id": "attempt-1",
            "title": "Replay probe",
            "idea": "Test whether replay detects a changed snapshot.",
            "mechanism": "A fixed snapshot prevents backdated evidence from changing history.",
            "failure_condition": "The snapshot changes.",
            "assumptions": [],
            "competing_explanations": [],
            "differentiator": "Compare snapshot hashes.",
            "available_at": "2026-01-01T00:00:00+00:00",
            "gpu_count": 2,
            "data_ready": True,
            "checkpoint_ready": True,
            "pilot_hours": 24,
            "storage_gb": 100,
            "baseline_first": False,
            "task": "research",
            "domain": "research",
        }

    def get_attempt(self, attempt_id):
        return self.attempt

    def hybrid_retrieve(self, attempt, embedding, cutoff, limit=6, *, match_all=False):
        self.search_query = attempt
        self.search_all = match_all
        return getattr(self, "candidates", [])[:limit]

    def evidence_for_attempts(self, attempt_ids, cutoff):
        return getattr(self, "evidence", {})

    def snapshot_hash(self, cutoff):
        return self.snapshot

    def save_evaluation(
        self, attempt_id, request, report, *, snapshot_hash, context_refs, replay_of=None
    ):
        self.runs[report["id"]] = report
        return report

    def get_run(self, run_id):
        return self.runs[run_id]

    def has_attempt(self, attempt_id):
        return attempt_id in self.existing_attempt_ids

    def import_card(self, card, embedding, *, attempt_id=None):
        self.existing_attempt_ids.add(attempt_id)
        self.imported.append((card, attempt_id))
        return {"id": attempt_id, "title": card.attempt.title}

    def list_source_documents(self):
        return self.source_documents


class FakeContext:
    configured = True

    def __init__(self):
        self.states = {}
        self.revisions = {}

    def list_kind(self, kind):
        if kind not in self.states:
            return []
        text, revision = self.states[kind]
        return [
            {
                "artifact": {"artifact_id": f"{kind}-artifact", "revision": revision},
                "content": {"kind": kind, "text": text},
            }
        ]

    def save_state(self, kind, text):
        revision = self.revisions.get(kind, 0) + 1
        self.revisions[kind] = revision
        self.states[kind] = (text, revision)
        return {
            "artifact": {"artifact_id": f"{kind}-artifact", "revision": revision},
            "content": {"kind": kind, "text": text},
        }


def test_replay_rejects_backdated_snapshot_changes():
    store = FakeStore()
    service = ResearchService(
        store,
        HashingEmbedder(),
        DeterministicComparator(),
        PowerContextAdapter(Settings(powercontext_url="")),
    )
    original = service.run_evaluation(
        EvaluationRunCreate(attempt_id="attempt-1", cutoff=datetime(2026, 2, 1, tzinfo=UTC))
    )
    store.snapshot = ("snapshot-after-backdated-write", {"attempts": 1, "evidence": 1})
    replay = service.replay(
        ReplayCreate(source_run_id=original["id"], expected_decision="INSUFFICIENT_EVIDENCE")
    )
    assert replay["regression"]["passed"] is False
    assert replay["regression"]["assertions"]["snapshot_integrity"] is False
    assert replay["regression"]["assertions"]["cutoff_integrity"] is True


def test_candidate_must_be_available_at_cutoff():
    store = FakeStore()
    store.attempt["available_at"] = "2026-02-02T00:00:00+00:00"
    service = ResearchService(
        store,
        HashingEmbedder(),
        DeterministicComparator(),
        PowerContextAdapter(Settings(powercontext_url="")),
    )

    with pytest.raises(CutoffViolationError, match="not available"):
        service.run_evaluation(
            EvaluationRunCreate(attempt_id="attempt-1", cutoff=datetime(2026, 2, 1, tzinfo=UTC))
        )

    assert store.runs == {}


def test_history_search_is_read_only_and_returns_source_evidence():
    store = FakeStore()
    store.candidates = [
        {
            "id": "historical-1",
            "title": "Prior attempt",
            "task": "research",
            "domain": "research",
            "historical_decision": "NO_GO",
            "available_at": "2026-01-01T00:00:00+00:00",
            "mechanism": "The earlier mechanism",
            "differentiator": "A narrower condition",
            "vector_distance": 0.2,
            "fts_score": 1.5,
            "fused_score": 0.01,
        },
        {
            "id": "historical-without-evidence",
            "title": "Unsourced attempt",
            "task": "research",
            "domain": "research",
            "historical_decision": None,
            "available_at": "2026-01-01T00:00:00+00:00",
            "mechanism": "An unsourced mechanism",
            "differentiator": "",
            "vector_distance": 0.1,
            "fts_score": 2.0,
            "fused_score": 0.02,
        },
    ]
    store.evidence = {
        "historical-1": [
            {
                "id": "evidence-1",
                "attempt_id": "historical-1",
                "title": "Original result",
                "locator": "examples/result.md#result",
                "excerpt": "The earlier attempt failed under this condition.",
            }
        ]
    }
    service = ResearchService(
        store,
        HashingEmbedder(),
        DeterministicComparator(),
        PowerContextAdapter(Settings(powercontext_url="")),
    )

    result = service.search_history("Can this proposed mechanism avoid the earlier failure?")

    assert store.search_query["mechanism"].startswith("Can this proposed")
    assert result["results"][0]["evidence"][0]["id"] == "evidence-1"
    assert len(result["results"]) == 1
    assert store.runs == {}


def test_source_import_is_chunked_traceable_and_idempotent():
    store = FakeStore()
    service = ResearchService(
        store,
        HashingEmbedder(),
        DeterministicComparator(),
        PowerContextAdapter(Settings(powercontext_url="")),
    )
    source_import = ResearchSourceImport(
        sources=[
            {
                "title": "External reliability study",
                "content": "A" * 8000 + "\n\nA result paragraph long enough to remain valid.",
                "locator": "local-library/reliability.md",
                "published_at": "2026-01-01T00:00:00Z",
            }
        ]
    )

    first = service.import_sources(source_import)
    second = service.import_sources(source_import)

    assert first["imported"] == 2
    assert first["skipped"] == 0
    assert second["imported"] == 0
    assert second["skipped"] == 2
    assert len(store.imported) == 2
    assert store.imported[0][0].evidence[0].locator.endswith("#part-1-of-2")
    assert store.imported[1][0].evidence[0].locator.endswith("#part-2-of-2")
    assert store.imported[0][0].attempt.available_at == datetime(2026, 1, 1, tzinfo=UTC)


def source_document(attempt_id, title, text, published_at):
    embedder = HashingEmbedder()
    return {
        "attempt_id": attempt_id,
        "title": title,
        "task": "research",
        "domain": "research",
        "available_at": published_at,
        "mechanism": text,
        "embedding": embedder.embed(f"{title} {text}"),
        "evidence_ids": [f"evidence-{attempt_id}"],
        "locators": [f"local-library/{attempt_id}.md"],
        "source_types": ["paper"],
        "excerpts": [text],
    }


def test_secretary_builds_traceable_knowledge_lines_and_persists_reviews():
    store = FakeStore()
    store.source_documents = [
        source_document(
            "attention",
            "Attention transformer",
            "transformer attention sequence model parallel training",
            "2017-06-12T00:00:00+00:00",
        ),
        source_document(
            "bert",
            "BERT transformer",
            "transformer attention sequence model bidirectional pretraining",
            "2018-10-11T00:00:00+00:00",
        ),
        source_document(
            "control",
            "Reinforcement control",
            "reinforcement policy reward environment control",
            "2020-01-01T00:00:00+00:00",
        ),
    ]
    context = FakeContext()
    service = ResearchService(
        store,
        HashingEmbedder(),
        DeterministicComparator(),
        context,
    )

    first = service.run_secretary()

    assert first["source_count"] == 3
    assert first["new_source_count"] == 3
    line = next(item for item in first["proposals"] if item["kind"] == "knowledge_line")
    orphan = next(item for item in first["proposals"] if item["kind"] == "orphan")
    assert set(line["source_ids"]) == {"attention", "bert"}
    assert line["evidence_ids"] == ["evidence-attention", "evidence-bert"]
    assert line["sources"][0]["locator"].startswith("local-library/")
    assert orphan["source_ids"] == ["control"]
    assert first["workspace"]["revision"] == 1
    assert first["context"] is None
    assert "secretary_context" not in context.states

    second = service.run_secretary()
    assert second["new_source_count"] == 0
    assert second["proposals"][0]["id"] == line["id"]
    assert second["proposals"][0]["status"] == "proposed"

    accepted = service.review_secretary(
        SecretaryReviewCreate(
            proposal_id=line["id"], status="accepted", note="Use as transformer context"
        )
    )
    assert accepted["accepted_count"] == 1
    assert accepted["proposals"][0]["status"] == "accepted"
    saved_context = json.loads(context.states["secretary_context"][0])
    assert saved_context["accepted_lines"][0]["proposal_id"] == line["id"]
    assert saved_context["accepted_lines"][0]["locators"] == [
        "local-library/attention.md",
        "local-library/bert.md",
    ]

    reloaded = service.get_secretary()
    assert reloaded["accepted_count"] == 1
    assert reloaded["proposals"][0]["review_note"] == "Use as transformer context"

    rerun = service.run_secretary()
    assert rerun["accepted_count"] == 1
    assert rerun["proposals"][0]["status"] == "accepted"
