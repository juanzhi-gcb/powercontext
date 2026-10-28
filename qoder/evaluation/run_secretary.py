from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_API = os.getenv("NULLPATH_API_URL", "http://127.0.0.1:8080/api").rstrip("/")
STATE_HOME = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
DEFAULT_OUTPUT = STATE_HOME / "nullpath" / "secretary-last-run.json"


def request(api: str, path: str, payload: dict[str, Any], timeout: int) -> Any:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{api}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"POST {req.full_url} returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Cannot reach {api}. Start the local Compose stack before running the secretary."
        ) from error


def receipt(api: str, report: dict[str, Any]) -> dict[str, Any]:
    proposals = report.get("proposals", [])
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for proposal in proposals:
        by_kind[proposal["kind"]] = by_kind.get(proposal["kind"], 0) + 1
        by_status[proposal["status"]] = by_status.get(proposal["status"], 0) + 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "api": api,
        "run_id": report.get("run_id"),
        "secretary_generated_at": report.get("generated_at"),
        "source_count": report.get("source_count", 0),
        "new_source_count": report.get("new_source_count", 0),
        "proposal_count": len(proposals),
        "accepted_count": report.get("accepted_count", 0),
        "by_kind": by_kind,
        "by_status": by_status,
        "workspace": report.get("workspace"),
        "context": report.get("context"),
        "proposals": [
            {
                "id": proposal["id"],
                "kind": proposal["kind"],
                "title": proposal["title"],
                "status": proposal["status"],
                "confidence": proposal["confidence"],
                "source_ids": proposal["source_ids"],
            }
            for proposal in proposals
        ],
        "note": (
            "Deterministic secretary receipt. It contains no source excerpts and makes no model calls; "
            "proposals stay pending until a human reviews them."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the NullPath research secretary against a local API without any LLM calls."
    )
    parser.add_argument("--api", default=DEFAULT_API, help="NullPath API base URL")
    parser.add_argument("--timeout", type=int, default=180, help="request timeout in seconds")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="receipt path; defaults outside the repository to keep local source titles private",
    )
    args = parser.parse_args()

    report = request(args.api.rstrip("/"), "/secretary/runs", {}, args.timeout)
    data = receipt(args.api.rstrip("/"), report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    print(
        f"Secretary {data['run_id']}: {data['source_count']} sources, "
        f"{data['new_source_count']} new, {data['proposal_count']} proposals, "
        f"{data['accepted_count']} accepted."
    )
    for kind, count in sorted(data["by_kind"].items()):
        print(f"  {kind}: {count}")
    print(f"Receipt: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)
