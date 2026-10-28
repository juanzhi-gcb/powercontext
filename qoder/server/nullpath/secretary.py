from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

KIND_ORDER = {"knowledge_line": 0, "near_duplicate": 1, "orphan": 2}
STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "using",
    "into",
    "than",
    "for",
    "are",
    "was",
    "were",
    "our",
    "their",
    "can",
    "not",
    "but",
    "research",
    "paper",
    "study",
    "method",
    "results",
    "all",
    "also",
    "one",
    "two",
    "three",
    "new",
    "based",
    "show",
    "shows",
    "used",
    "use",
    "uses",
    "may",
    "more",
    "most",
    "such",
    "these",
    "those",
    "has",
    "have",
    "had",
    "its",
    "only",
    "over",
    "after",
    "both",
    "each",
    "other",
    "same",
    "then",
    "there",
    "which",
    "when",
    "where",
    "while",
    "would",
    "could",
    "should",
    "might",
    "must",
    "however",
    "within",
    "without",
    "under",
    "between",
    "during",
    "via",
    "资料",
    "研究",
    "方法",
    "结果",
    "我们",
    "以及",
    "一个",
    "通过",
}
TITLE_NOISE = {
    "abstract",
    "achieve",
    "achieves",
    "approach",
    "approaches",
    "architecture",
    "architectures",
    "arxiv",
    "baseline",
    "baselines",
    "compare",
    "compared",
    "comparison",
    "data",
    "dataset",
    "datasets",
    "demonstrate",
    "demonstrates",
    "evaluation",
    "evaluations",
    "evidence",
    "experiment",
    "experiments",
    "following",
    "imported",
    "improve",
    "improvement",
    "improvements",
    "improves",
    "including",
    "introduce",
    "introduces",
    "local",
    "loop",
    "method",
    "methods",
    "model",
    "models",
    "novel",
    "obtain",
    "obtains",
    "paper",
    "papers",
    "performance",
    "present",
    "presents",
    "propose",
    "proposed",
    "proposes",
    "respectively",
    "result",
    "results",
    "score",
    "scores",
    "significant",
    "significantly",
    "source",
    "state",
    "state-of-the-art",
    "art",
    "study",
    "studies",
    "system",
    "systems",
    "task",
    "tasks",
    "therefore",
    "thus",
    "validation",
    "wide",
    "range",
    "large",
    "small",
    "different",
    "additional",
    "recent",
    "conceptually",
    "empirically",
    "powerful",
    "simple",
    "https",
    "http",
    "www",
    "org",
    "abs",
    "et",
    "al",
}


def normalize(word: str) -> str:
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = {
        normalize(item)
        for item in re.findall(r"[a-z][a-z0-9_-]{2,}", lowered)
        if item not in STOPWORDS
    }
    chinese = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for index in range(len(run) - 1):
            term = run[index : index + 2]
            if term not in STOPWORDS:
                chinese.add(term)
    return words | chinese


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def base_locator(locator: str) -> str:
    return re.sub(r"#part-\d+-of-\d+$", "", locator)


def source_view(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": document["attempt_id"],
        "title": document["title"],
        "locator": document["locators"][0],
        "locators": document["locators"],
        "published_at": document["available_at"],
        "source_type": document["source_types"][0],
        "evidence_ids": document["evidence_ids"],
    }


def proposal_id(kind: str, source_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(source_ids)).encode()).hexdigest()[:16]
    return f"{kind}-{digest}"


def date_span(documents: list[dict[str, Any]]) -> str:
    dates = sorted(document["available_at"][:10] for document in documents)
    if not dates:
        return ""
    return dates[0] if dates[0] == dates[-1] else f"{dates[0]} – {dates[-1]}"


def common_terms(documents: list[dict[str, Any]], limit: int = 3) -> list[str]:
    counts: Counter[str] = Counter()
    for document in documents:
        counts.update(tokens(f"{document['title']} {document['excerpts'][0][:1200]}"))
    shared = [
        term
        for term, count in sorted(
            counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0])
        )
        if count >= 2 and term not in TITLE_NOISE
    ]
    return shared[:limit]


def line_title(documents: list[dict[str, Any]]) -> str:
    first = documents[0]["title"][:96]
    if len(documents) == 1:
        return first
    return f"{first} 等 {len(documents)} 份资料"


def line_summary(documents: list[dict[str, Any]], confidence: float) -> str:
    terms = common_terms(documents)
    topic = f"共享主题「{'、'.join(terms)}」" if terms else "主题相近"
    span = date_span(documents)
    suffix = f"，时间跨度 {span}" if span else ""
    return (
        f"{len(documents)} 份资料{topic}，共 "
        f"{sum(len(document['evidence_ids']) for document in documents)} 条可定位证据{suffix}。"
        f"连接强度 {confidence:.2f}；秘书只提出关联，不判断研究结论是否成立。"
    )


def pair_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, float, bool]:
    lexical = jaccard(
        tokens(f"{left['title']} {left['excerpts'][0][:2000]}"),
        tokens(f"{right['title']} {right['excerpts'][0][:2000]}"),
    )
    semantic = max(0.0, cosine(left["embedding"], right["embedding"]))
    same_document = base_locator(left["locators"][0]) == base_locator(right["locators"][0])
    confidence = round(0.65 * lexical + 0.35 * semantic, 4)
    related = same_document or lexical >= 0.10 or semantic >= 0.86
    return confidence, semantic, related


def build_proposals(
    documents: list[dict[str, Any]],
    reviews: dict[str, dict[str, Any]],
    previous_source_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    documents = sorted(documents, key=lambda item: (item["available_at"], item["title"]))
    new_source_ids = sorted(
        document["attempt_id"]
        for document in documents
        if document["attempt_id"] not in previous_source_ids
    )
    if not documents:
        return [], new_source_ids

    parents = list(range(len(documents)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    edges: list[tuple[float, float, int, int]] = []
    for left in range(len(documents)):
        for right in range(left + 1, len(documents)):
            confidence, semantic, related = pair_score(documents[left], documents[right])
            edges.append((confidence, semantic, left, right))
            if related:
                union(left, right)

    clusters: dict[int, list[dict[str, Any]]] = {}
    for index, document in enumerate(documents):
        clusters.setdefault(find(index), []).append(document)

    proposals: list[dict[str, Any]] = []
    for confidence, semantic, left, right in edges:
        same_document = base_locator(documents[left]["locators"][0]) == base_locator(
            documents[right]["locators"][0]
        )
        if same_document or (semantic < 0.97 and confidence < 0.60):
            continue
        ids = sorted([documents[left]["attempt_id"], documents[right]["attempt_id"]])
        proposals.append(
            {
                "id": proposal_id("near_duplicate", ids),
                "kind": "near_duplicate",
                "title": f"可能重复：{documents[left]['title'][:70]} / {documents[right]['title'][:70]}",
                "summary": (
                    f"两段资料的主题和表述高度接近（连接强度 {confidence:.2f}）。"
                    "重复计入会放大同一证据的权重。"
                ),
                "next_action": "核对 locator 与全文，确认是否为同一资料的不同版本；若是，保留更精确的一份。",
                "source_ids": ids,
                "evidence_ids": documents[left]["evidence_ids"] + documents[right]["evidence_ids"],
                "sources": [source_view(documents[left]), source_view(documents[right])],
                "confidence": confidence,
            }
        )

    for cluster in sorted(clusters.values(), key=lambda items: (-len(items), items[0]["title"])):
        ids = [document["attempt_id"] for document in cluster]
        if len(cluster) == 1:
            kind = "orphan"
            confidence = 0.0
            title = cluster[0]["title"][:160]
            summary = "这份资料目前没有连接到其他研究资料，可能还没有形成可复用的知识线。"
            next_action = "补充一份独立来源，或检查标题与摘要是否包含足够具体的机制信息。"
        else:
            kind = "knowledge_line"
            scored = [
                pair_score(cluster[left], cluster[right])[0]
                for left in range(len(cluster))
                for right in range(left + 1, len(cluster))
            ]
            confidence = round(sum(scored) / len(scored), 4) if scored else 0.0
            title = line_title(cluster)
            summary = line_summary(cluster, confidence)
            next_action = "核对这些资料是否支持同一机制；如果只是主题相近，保留为不同知识线。"
        proposals.append(
            {
                "id": proposal_id(kind, ids),
                "kind": kind,
                "title": title,
                "summary": summary,
                "next_action": next_action,
                "source_ids": ids,
                "evidence_ids": [
                    evidence_id for document in cluster for evidence_id in document["evidence_ids"]
                ],
                "sources": [source_view(document) for document in cluster],
                "confidence": confidence,
            }
        )

    for proposal in proposals:
        review = reviews.get(proposal["id"], {})
        proposal["status"] = review.get("status", "proposed")
        proposal["review_note"] = review.get("note", "")
        proposal["reviewed_at"] = review.get("reviewed_at")

    proposals.sort(
        key=lambda item: (KIND_ORDER.get(item["kind"], 9), -len(item["source_ids"]), item["title"])
    )
    return proposals, new_source_ids


def secretary_context(proposals: list[dict[str, Any]], generated_at: str) -> str:
    accepted = [proposal for proposal in proposals if proposal["status"] == "accepted"]
    payload = {
        "schema": "nullpath.secretary-context.v1",
        "updated_at": generated_at,
        "accepted_lines": [
            {
                "proposal_id": proposal["id"],
                "kind": proposal["kind"],
                "title": proposal["title"],
                "summary": proposal["summary"],
                "source_ids": proposal["source_ids"],
                "locators": [
                    locator for source in proposal["sources"] for locator in source["locators"]
                ],
                "next_action": proposal["next_action"],
            }
            for proposal in accepted[:20]
        ],
        "open_questions": [proposal["next_action"] for proposal in accepted[:10]],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
