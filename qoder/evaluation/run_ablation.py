from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from nullpath.comparator import DeterministicComparator
from nullpath.config import Settings
from nullpath.embeddings import HashingEmbedder
from nullpath.evaluation import evaluate
from nullpath.service import ResearchService
from nullpath.store import SeekDBStore

ROOT = Path(__file__).resolve().parents[1]
MODES = {"vector": ("vector",), "fulltext": ("fts",), "hybrid": ("vector", "fts")}


def main() -> int:
    settings = replace(
        Settings.from_env(),
        seekdb_database=os.getenv("NULLPATH_VALIDATION_DATABASE", "nullpath_validation"),
    )
    store = SeekDBStore(settings)
    embedder = HashingEmbedder(settings.embedding_dimensions)
    comparator = DeterministicComparator()
    service = ResearchService(store, embedder, comparator, context=None)
    attempts = {item["title"]: store.get_attempt(item["id"]) for item in store.list_attempts()}
    cases = json.loads((ROOT / "evaluation" / "golden_cases.json").read_text())
    results = []

    for mode, channels in MODES.items():
        for case in cases:
            attempt = attempts[case["title"]]
            cutoff = datetime.fromisoformat(case["cutoff"])
            embedding = embedder.embed(service.embedding_text(attempt))
            candidates = store.hybrid_retrieve(
                attempt, embedding, cutoff, channels=channels
            )
            evidence = store.evidence_for_attempts(
                [item["id"] for item in candidates], cutoff
            )
            report = evaluate(
                attempt,
                cutoff,
                candidates,
                evidence,
                comparator,
                comparator.version,
                embedder.version,
                [],
                [],
            )
            recalled = set(report["evidence_ids"])
            required = set(case["required_evidence_ids"])
            forbidden = set(case["forbidden_evidence_ids"])
            passed = (
                report["machine_decision"] == case["expected_decision"]
                and required <= recalled
                and not forbidden & recalled
            )
            results.append(
                {
                    "mode": mode,
                    "title": case["title"],
                    "passed": passed,
                    "decision": report["machine_decision"],
                    "expected_decision": case["expected_decision"],
                    "required_evidence_recalled": required <= recalled,
                    "forbidden_evidence_recalled": sorted(forbidden & recalled),
                    "recalled_attempt_ids": [item["attempt_id"] for item in report["comparisons"]],
                    "evidence_ids": report["evidence_ids"],
                }
            )
        mode_results = [item for item in results if item["mode"] == mode]
        passed_count = sum(item["passed"] for item in mode_results)
        print(f"{mode:8s} {passed_count}/{len(mode_results)} cases passed")

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": settings.seekdb_database,
        "cases": results,
        "note": "Each mode reruns the real seekdb ranking path and deterministic decision policy; no LLM is used.",
    }
    destination = ROOT / "evidence" / "ablation-results.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(results)} ablation runs to {destination}")
    return 0 if all(item["passed"] for item in results if item["mode"] == "hybrid") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)
