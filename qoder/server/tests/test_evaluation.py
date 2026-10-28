from datetime import UTC, datetime

import pytest

from nullpath.comparator import DeterministicComparator
from nullpath.evaluation import evaluate

CUTOFF = datetime(2026, 2, 2, tzinfo=UTC)


def attempt(**overrides):
    value = {
        "id": "candidate",
        "title": "Candidate",
        "idea": "Test a mechanism under a controlled intervention.",
        "mechanism": "Reliability and complementarity determine collaboration performance.",
        "failure_condition": "A trivial estimator explains the observation.",
        "assumptions": [],
        "competing_explanations": ["Weighted baseline"],
        "differentiator": "Restrict the observation map to test identifiability.",
        "available_at": CUTOFF.isoformat(),
        "gpu_count": 2,
        "data_ready": True,
        "checkpoint_ready": True,
        "pilot_hours": 24,
        "storage_gb": 100,
        "baseline_first": False,
    }
    value.update(overrides)
    return value


def candidate(**overrides):
    value = {
        "id": "historical",
        "title": "Historical",
        "task": "research",
        "domain": "research",
        "mechanism": "Reliability and complementarity determine collaboration performance.",
        "historical_decision": "NO_GO",
        "available_at": "2026-01-01T00:00:00+00:00",
        "vector_distance": 0.1,
        "fts_score": 2.0,
        "vector_rank": 1,
        "fts_rank": 1,
        "fused_score": 0.02,
    }
    value.update(overrides)
    return value


def evidence():
    return {
        "id": "evidence-1",
        "attempt_id": "historical",
        "title": "Located review",
        "locator": "examples/review.md#result",
        "excerpt": "The controlled result limits the original claim.",
        "stance": "limits",
        "published_at": "2026-01-01T00:00:00+00:00",
    }


def run(
    candidate_attempt, candidates=None, evidence_by_attempt=None, context=None, comparator=None
):
    return evaluate(
        candidate_attempt,
        CUTOFF,
        candidates if candidates is not None else [candidate()],
        evidence_by_attempt if evidence_by_attempt is not None else {"historical": [evidence()]},
        comparator or DeterministicComparator(),
        "test-comparator-v1",
        "test-embedding-v1",
        context or [],
        [],
    )


@pytest.mark.parametrize(
    ("field", "value", "check_name"),
    [
        ("data_ready", False, "engineering.data"),
        ("checkpoint_ready", False, "engineering.checkpoint"),
        ("gpu_count", 1, "engineering.gpu"),
        ("pilot_hours", 49, "engineering.closed_loop"),
        ("storage_gb", 49, "engineering.storage"),
        ("baseline_first", True, "process.problem_first"),
    ],
)
def test_deterministic_gates_fail_closed(field, value, check_name):
    report = run(attempt(**{field: value}))
    assert report["machine_decision"] == "NO_GO"
    assert report["reason_code"] == "DETERMINISTIC_GATE_FAILED"
    assert next(item for item in report["checks"] if item["name"] == check_name)["status"] == "fail"


def test_configured_baseline_gate_can_be_disabled():
    context = [{"kind": "research_constitution", "text": '{"problem_before_baseline": false}'}]
    report = run(attempt(baseline_first=True), context=context)
    assert report["machine_decision"] == "CONDITIONAL_GO"
    assert (
        next(item for item in report["checks"] if item["name"] == "process.problem_first")["status"]
        == "pass"
    )


def test_identical_mechanism_without_differentiator_is_repackaged():
    report = run(attempt(differentiator=""))
    assert report["machine_decision"] == "NO_GO"
    assert report["reason_code"] == "MECHANISM_REPACKAGED"


def test_differentiated_mechanism_requires_minimum_experiment():
    report = run(attempt())
    assert report["machine_decision"] == "CONDITIONAL_GO"
    assert (
        report["minimal_experiment"]["control"]
        == "Run the strongest competing explanation: Weighted baseline"
    )


def test_no_evidence_is_not_a_negative_verdict():
    report = run(attempt(), evidence_by_attempt={"historical": []})
    assert report["machine_decision"] == "INSUFFICIENT_EVIDENCE"
    assert report["reason_code"] == "NO_LOCATABLE_HISTORICAL_EVIDENCE"


def test_no_candidates_is_insufficient_evidence():
    report = run(attempt(), candidates=[], evidence_by_attempt={})
    assert report["machine_decision"] == "INSUFFICIENT_EVIDENCE"


def test_unknown_comparator_citation_invalidates_comparison():
    class InvalidComparator:
        version = "invalid-test"

        def compare(self, candidate, historical, evidence):
            return {"similarity": 0.9, "difference": "same", "evidence_ids": ["invented"]}

    report = run(attempt(), comparator=InvalidComparator())
    assert report["machine_decision"] == "INSUFFICIENT_EVIDENCE"
    assert report["reason_code"] == "COMPARISON_OUTPUT_INVALID"
    assert report["evidence_ids"] == []
