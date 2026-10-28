from __future__ import annotations

import argparse
import json
from pathlib import Path

from .comparator import build_comparator
from .config import Settings
from .context import PowerContextAdapter
from .embeddings import build_embedder
from .models import ArchiveImport
from .service import ResearchService
from .store import SeekDBStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Import reviewed NullPath archive cards")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    store = SeekDBStore(settings)
    store.init_schema()
    context = PowerContextAdapter(settings)
    service = ResearchService(store, build_embedder(), build_comparator(), context)
    archive = ArchiveImport.model_validate(json.loads(args.archive.read_text()))
    imported = service.import_archive(archive)
    if context.configured:
        context.save_state(
            "research_constitution",
            json.dumps(
                {
                    "min_gpu_count": 2,
                    "max_pilot_hours": 48,
                    "min_storage_gb": 50,
                    "problem_before_baseline": True,
                },
                separators=(",", ":"),
            ),
        )
    print(json.dumps({"imported": len(imported), "attempt_ids": [item["id"] for item in imported]}))


if __name__ == "__main__":
    main()
