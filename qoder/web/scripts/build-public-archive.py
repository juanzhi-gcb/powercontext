#!/usr/bin/env python3
"""Build the public archive corpus and its seekdb-compatible embeddings.

Run from the repository root:
  python3 qoder/web/scripts/build-public-archive.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
WEB = HERE.parents[1]
QODER = HERE.parents[2]
SERVER = QODER / "server"
sys.path.insert(0, str(SERVER))

from nullpath.embeddings import HashingEmbedder  # noqa: E402

ALIASES = {
    "moon": ["先验角色", "先验角色纠缠", "确认偏误", "confirmation bias", "跨方法", "单方法伪影", "prior-role", "cross-method"],
    "ibml": ["可靠性", "互补性", "协作性能", "相图", "可识别性", "reliability", "complementarity", "collaboration", "phase diagram", "identifiability"],
    "codealign": ["表示对齐", "代码迁移", "数据组成", "检查点", "representation alignment", "code alignment", "code transfer", "checkpoint"],
    "attention": ["自注意力", "注意力机制", "长距离依赖", "循环结构", "序列转换", "self-attention", "attention", "recurrence", "long-range dependencies", "transformer", "sequence transduction"],
    "bert": ["双向编码器", "预训练", "语言理解", "微调", "bidirectional", "pre-training", "language understanding", "fine-tune", "transformer", "transformers"],
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def aliases_for(title: str) -> list[str]:
    lowered = title.lower()
    for key, values in ALIASES.items():
        if key in lowered:
            return values
    return []


def paper_record(fixture: Path, *, task: str, published: str, evidence_id: str) -> dict:
    lines = fixture.read_text(encoding="utf-8").strip().splitlines()
    title = lines[0].lstrip("# ").strip()
    abstract_lines = []
    for line in lines[1:]:
        if line.startswith("Source:"):
            continue
        if line.strip():
            abstract_lines.append(line.strip())
    abstract = "\n\n".join(abstract_lines)
    source = next((line for line in lines if line.startswith("Source:")), "")
    locator = "https://arxiv.org/abs/" + (re.search(r"arXiv:([0-9.]+)", source).group(1) if re.search(r"arXiv:([0-9.]+)", source) else "")
    return {
        "id": "public-" + slug(title.split(":")[0]),
        "title": title,
        "idea": abstract,
        "mechanism": abstract,
        "failure_condition": "External source record; no failure condition declared.",
        "task": task,
        "domain": "research",
        "assumptions": [],
        "search_terms": aliases_for(title),
        "historical_decision": None,
        "available_at": published,
        "evidence": [
            {
                "id": evidence_id,
                "source_type": "paper",
                "title": title,
                "locator": locator,
                "excerpt": abstract,
                "stance": "supports",
                "published_at": published,
            }
        ],
    }


def main() -> None:
    archive = json.loads((QODER / "examples" / "archive.json").read_text(encoding="utf-8"))
    records = []
    for card in archive["cards"]:
        attempt = card["attempt"]
        records.append(
            {
                "id": slug(attempt["title"]),
                "title": attempt["title"],
                "idea": attempt["idea"],
                "mechanism": attempt["mechanism"],
                "failure_condition": attempt["failure_condition"],
                "task": attempt["task"],
                "domain": attempt["domain"],
                "assumptions": attempt.get("assumptions", []),
                "search_terms": aliases_for(attempt["title"]),
                "historical_decision": card.get("historical_decision"),
                "available_at": attempt["available_at"],
                "evidence": card.get("evidence", []),
            }
        )
    records.append(
        paper_record(
            QODER / "evidence" / "library-import-fixture.md",
            task="language-model-analysis",
            published="2017-06-12T00:00:00Z",
            evidence_id="evidence-public-attention",
        )
    )
    records.append(
        paper_record(
            QODER / "evidence" / "library-import-fixture-bert.md",
            task="language-model-analysis",
            published="2018-10-11T00:00:00Z",
            evidence_id="evidence-public-bert",
        )
    )

    embedder = HashingEmbedder(64)
    embeddings = {}
    for record in records:
        text = " ".join(
            [
                record["title"],
                record["idea"],
                record["mechanism"],
                record["failure_condition"],
                *record["assumptions"],
                *record.get("search_terms", []),
            ]
        )
        embeddings[record["id"]] = embedder.embed(text)

    corpus = {
        "version": "public-archive-2026-10-28",
        "retrieval": "browser-vector-fts-rrf-v1",
        "records": records,
    }
    (WEB / "src" / "public-archive.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (WEB / "src" / "public-archive-embeddings.json").write_text(
        json.dumps(embeddings, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "records": len(records),
                "with_evidence": sum(1 for record in records if record["evidence"]),
                "embedding_version": embedder.version,
            }
        )
    )


if __name__ == "__main__":
    main()
