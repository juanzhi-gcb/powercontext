from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("NULLPATH_API_URL", "http://127.0.0.1:8081/api").rstrip("/")


def request(path: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{req.method} {req.full_url} returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Cannot reach {API}. Start the Compose validation profile and wait for bootstrap."
        ) from error


def main() -> int:
    cases = json.loads((ROOT / "evaluation" / "golden_cases.json").read_text())
    attempts = {item["title"]: item for item in request("/attempts")}
    missing = [case["title"] for case in cases if case["title"] not in attempts]
    if missing:
        raise RuntimeError(f"Seed attempts are missing: {', '.join(missing)}")

    results = []
    for case in cases:
        original = request(
            "/evaluation-runs",
            {
                "attempt_id": attempts[case["title"]]["id"],
                "cutoff": case["cutoff"],
                "use_context": True,
            },
        )
        replay = request(
            "/replays",
            {
                "source_run_id": original["id"],
                "expected_decision": case["expected_decision"],
                "required_evidence_ids": case["required_evidence_ids"],
                "forbidden_evidence_ids": case["forbidden_evidence_ids"],
            },
        )
        passed = (
            original["machine_decision"] == case["expected_decision"]
            and replay["regression"]["passed"]
        )
        results.append(
            {
                "title": case["title"],
                "passed": passed,
                "expected_decision": case["expected_decision"],
                "actual_decision": original["machine_decision"],
                "reason_code": original["reason_code"],
                "source_run_id": original["id"],
                "replay_run_id": replay["id"],
                "evidence_ids": original["evidence_ids"],
                "assertions": replay["regression"]["assertions"],
            }
        )
        print(
            f"{'PASS' if passed else 'FAIL'}  {case['title']}: "
            f"{original['machine_decision']} / {original['reason_code']}"
        )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "api": API,
        "passed": all(item["passed"] for item in results),
        "cases": results,
        "note": "Results come from the configured local API; demo cards are reconstructed validation fixtures, not original laboratory logs.",
    }
    destination = ROOT / "evidence" / "golden-results.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(results)} results to {destination}")
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)
