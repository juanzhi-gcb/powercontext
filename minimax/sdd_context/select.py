"""Turn a task description into a verifiable development context.

Selection is deterministic and explainable: candidate documents are ranked with
TF-IDF over the inverted index stored in seekdb/OceanBase, then expanded along
the explicit link graph (spec -> code, test -> spec, test -> code).
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database
from .terms import dedupe, idf, tf_weight, tokenize

MAX_SPEC_ITEMS = 8
MAX_CODE_ITEMS = 8
MAX_TARGET_TESTS = 12
MAX_REGRESSION_TESTS = 20
RELATIVE_CUTOFF = 0.28


def _load_corpus(database: Database, project_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]]]:
    rows = database.query(
        """
        SELECT doc_id, doc_type, path, symbol, title, start_line, end_line,
               revision, checksum, keywords
          FROM sdd_documents
         WHERE project_id = %s
        """,
        (project_id,),
    )
    corpus = {row["doc_id"]: row for row in rows}
    postings: dict[str, dict[str, float]] = defaultdict(dict)
    for row in database.query(
        """
        SELECT p.term, p.doc_id, p.tf
          FROM sdd_postings p
          JOIN sdd_documents d ON d.doc_id = p.doc_id
         WHERE d.project_id = %s
        """,
        (project_id,),
    ):
        postings[row["doc_id"]][row["term"]] = float(row["tf"])
    return corpus, postings


def _rank(
    task: str,
    corpus: dict[str, dict[str, Any]],
    postings: dict[str, dict[str, float]],
    doc_type: str,
) -> list[dict[str, Any]]:
    query_terms = Counter(tokenize(task))
    if not query_terms:
        return []
    terms = dedupe(list(query_terms))[:60]
    df: Counter[str] = Counter()
    for doc_terms in postings.values():
        for term in doc_terms:
            if term in query_terms:
                df[term] += 1
    total_docs = max(len(corpus), 1)

    ranked: list[dict[str, Any]] = []
    for doc_id, meta in corpus.items():
        if meta["doc_type"] != doc_type:
            continue
        doc_terms = postings.get(doc_id, {})
        score = 0.0
        matched: list[str] = []
        for term, query_count in query_terms.items():
            tf = doc_terms.get(term)
            if not tf:
                continue
            weight = tf_weight(tf) * idf(df.get(term, 0), total_docs) * (1.0 + math.log(query_count))
            if weight <= 0:
                continue
            score += weight
            matched.append(term)
        if score <= 0:
            continue
        length = sum(doc_terms.values()) or 1.0
        ranked.append(
            {
                "doc_id": doc_id,
                "meta": meta,
                "score": round(score / math.sqrt(length), 6),
                "matched_terms": sorted(matched, key=lambda item: (-len(item), item))[:12],
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["doc_id"]))
    return ranked


def _apply_cutoff(ranked: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not ranked:
        return []
    floor = ranked[0]["score"] * RELATIVE_CUTOFF
    return [item for item in ranked if item["score"] >= floor][:limit]


def _links(database: Database, project_id: str) -> list[dict[str, str]]:
    return database.query(
        """
        SELECT l.src_id, l.dst_id, l.kind
          FROM sdd_links l
          JOIN sdd_documents d ON d.doc_id = l.src_id
         WHERE d.project_id = %s
        """,
        (project_id,),
    )


def _outgoing(links: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    graph: dict[str, list[dict[str, str]]] = defaultdict(list)
    for link in links:
        graph[link["src_id"]].append(link)
    return graph


def _incoming(links: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    graph: dict[str, list[dict[str, str]]] = defaultdict(list)
    for link in links:
        graph[link["dst_id"]].append(link)
    return graph


def _read_lines(settings: Settings, path: str) -> list[str] | None:
    file_path = settings.workspace / path
    if not file_path.is_file():
        return None
    return file_path.read_text(encoding="utf-8").splitlines()


def verify_source(settings: Settings, meta: dict[str, Any]) -> dict[str, Any]:
    """Check that a stored document still matches the file on disk."""

    lines = _read_lines(settings, meta["path"])
    if lines is None:
        return {"verified": False, "reason": "file missing on disk"}
    start = max(int(meta["start_line"]) - 1, 0)
    end = int(meta["end_line"])
    if meta["doc_type"] == "spec":
        # Section bodies exclude the markdown heading, so re-parse the file.
        from .ingest import parse_spec_file

        try:
            docs = parse_spec_file(settings, settings.workspace / meta["path"])
        except Exception as exc:  # noqa: BLE001 - report, do not crash the context
            return {"verified": False, "reason": f"cannot re-parse specification: {exc}"}
        for doc in docs:
            if doc.doc_id == meta["doc_id"]:
                return {
                    "verified": doc.checksum == meta["checksum"],
                    "reason": "content matches file" if doc.checksum == meta["checksum"] else "content drifted",
                    "current_checksum": doc.checksum,
                }
        return {"verified": False, "reason": "specification item no longer exists"}
    segment = "\n".join(lines[start:end])
    digest = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    if digest == meta["checksum"]:
        return {"verified": True, "reason": "content matches file"}
    return {
        "verified": False,
        "reason": "file changed since the last import",
        "current_checksum": digest,
    }


def _source_block(settings: Settings, meta: dict[str, Any]) -> dict[str, Any]:
    verification = verify_source(settings, meta)
    return {
        "path": meta["path"],
        "start_line": int(meta["start_line"]),
        "end_line": int(meta["end_line"]),
        "revision": int(meta["revision"]),
        "checksum": meta["checksum"],
        "verified": verification["verified"],
        "verification": verification["reason"],
    }


def build_context(
    settings: Settings,
    database: Database,
    task: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    corpus, postings = _load_corpus(database, settings.project_id)
    links = _links(database, settings.project_id)
    outgoing = _outgoing(links)
    incoming = _incoming(links)

    ranked_specs = _apply_cutoff(_rank(task, corpus, postings, "spec"), MAX_SPEC_ITEMS)
    if not ranked_specs:
        raise LookupError("no specification item matches this task; run ingest first?")

    query_terms = dedupe(tokenize(task))
    task_identifiers = {term for term in query_terms if "_" in term or term.isascii() and len(term) > 3}

    spec_ids = [item["doc_id"] for item in ranked_specs]
    spec_id_set = set(spec_ids)

    # Code: linked from selected specs, mentioned in the task, or exercised by
    # the tests that cover the selected specs.
    code_reasons: dict[str, list[str]] = defaultdict(list)
    for spec_doc_id in spec_ids:
        for link in outgoing.get(spec_doc_id, []):
            if link["kind"] == "spec-code" and corpus.get(link["dst_id"], {}).get("doc_type") == "code":
                code_reasons[link["dst_id"]].append(f"linked to {spec_doc_id.split(':', 1)[1]}")

    for doc_id, meta in corpus.items():
        if meta["doc_type"] != "code":
            continue
        short = (meta["symbol"] or "").split(".")[-1].lower()
        if short and short in task_identifiers:
            code_reasons[doc_id].append("symbol named in the task")

    # The focus specification is the highest-ranked one: its requirement items are
    # what the task changes, so their tests are the target suite. Tests for the
    # other selected items guard behaviour that must not regress.
    focus_spec_id = (ranked_specs[0]["meta"]["symbol"] or "").split("#", 1)[0]
    focus_doc_ids = {
        item["doc_id"]
        for item in ranked_specs
        if (item["meta"]["symbol"] or "").startswith(f"{focus_spec_id}#")
    }

    target_doc_ids: list[str] = []
    for doc_id, meta in corpus.items():
        if meta["doc_type"] != "test":
            continue
        if "regression" in _keywords(meta):
            continue
        covers = [link["dst_id"] for link in outgoing.get(doc_id, []) if link["kind"] == "test-spec"]
        if any(cover in focus_doc_ids for cover in covers):
            target_doc_ids.append(doc_id)
            for link in outgoing.get(doc_id, []):
                if link["kind"] == "test-code":
                    code_reasons[link["dst_id"]].append(f"exercised by {doc_id.split('::', 1)[-1]}")

    code_selected = sorted(code_reasons, key=lambda doc_id: (-len(code_reasons[doc_id]), doc_id))[:MAX_CODE_ITEMS]
    code_set = set(code_selected)

    regression_doc_ids = []
    for doc_id, meta in corpus.items():
        if meta["doc_type"] != "test" or doc_id in target_doc_ids:
            continue
        exercises = [link["dst_id"] for link in outgoing.get(doc_id, []) if link["kind"] == "test-code"]
        covers = [link["dst_id"] for link in outgoing.get(doc_id, []) if link["kind"] == "test-spec"]
        if any(exercise in code_set for exercise in exercises) or any(cover in spec_id_set for cover in covers):
            regression_doc_ids.append(doc_id)

    # --- render -------------------------------------------------------
    spec_items = []
    for item in ranked_specs:
        meta = item["meta"]
        spec_items.append(
            {
                "id": meta["symbol"],
                "spec_id": (meta["symbol"] or "").split("#", 1)[0],
                "title": meta["title"],
                "requirement": _content(database, meta["doc_id"]),
                "matched_terms": item["matched_terms"],
                "score": item["score"],
                "source": _source_block(settings, meta),
            }
        )

    code_items = []
    for doc_id in code_selected:
        meta = corpus[doc_id]
        code_items.append(
            {
                "doc_id": doc_id,
                "symbol": meta["symbol"],
                "path": meta["path"],
                "reason": _dedupe_reasons(code_reasons[doc_id]),
                "source": _source_block(settings, meta),
            }
        )

    def _test_item(doc_id: str) -> dict[str, Any]:
        meta = corpus[doc_id]
        covers = sorted(
            link["dst_id"].split(":", 1)[1]
            for link in outgoing.get(doc_id, [])
            if link["kind"] == "test-spec"
        )
        return {
            "node_id": f"{meta['path'].split('demo_project/', 1)[-1]}::{meta['symbol']}",
            "name": meta["symbol"],
            "path": meta["path"],
            "covers": covers,
            "source": _source_block(settings, meta),
        }

    target_tests = [_test_item(doc_id) for doc_id in sorted(target_doc_ids)[:MAX_TARGET_TESTS]]
    regression_tests = [_test_item(doc_id) for doc_id in sorted(regression_doc_ids)[:MAX_REGRESSION_TESTS]]

    return {
        "schema": "sdd-context/v1",
        "task_id": task_id or make_task_id(task),
        "task": task,
        "project_id": settings.project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ingest_run": run_id,
        "selection": {
            "method": "tf-idf over seekdb inverted index + spec/test/code link graph",
            "query_terms": query_terms[:40],
            "candidate_documents": len(corpus),
        },
        "spec_items": spec_items,
        "code": code_items,
        "tests": {"target": target_tests, "regression": regression_tests},
    }


def _keywords(meta: dict[str, Any]) -> list[str]:
    import json

    try:
        value = json.loads(meta.get("keywords") or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    direct: list[str] = []
    exercised: list[str] = []
    for reason in reasons:
        if reason.startswith("exercised by "):
            exercised.append(reason[len("exercised by ") :])
        elif reason not in direct:
            direct.append(reason)
    summary = direct[:3]
    if exercised:
        summary.append(f"exercised by {len(exercised)} tests")
    return summary


def _content(database: Database, doc_id: str) -> str:
    rows = database.query("SELECT content FROM sdd_documents WHERE doc_id = %s", (doc_id,))
    return rows[0]["content"] if rows else ""


def make_task_id(task: str) -> str:
    digest = hashlib.sha256(task.strip().encode("utf-8")).hexdigest()[:10]
    return f"task-{digest}"


def scope_id_for(settings: Settings, task_id: str) -> str:
    return f"sdd:{settings.project_id}:{task_id}"


def latest_run_id(database: Database, project_id: str) -> str | None:
    rows = database.query(
        "SELECT run_id FROM sdd_ingest_runs WHERE project_id = %s ORDER BY started_at DESC, run_id DESC LIMIT 1",
        (project_id,),
    )
    return rows[0]["run_id"] if rows else None


def context_for_prompt(context: dict[str, Any]) -> str:
    """Render the context as the prompt block handed to the coding model."""

    lines: list[str] = []
    lines.append("## 适用的规格条目 (specification)")
    for item in context["spec_items"]:
        src = item["source"]
        lines.append(
            f"### {item['id']} {item['title']}  [{src['path']}:{src['start_line']}-{src['end_line']}]"
        )
        lines.append(item["requirement"].strip())
        lines.append("")
    lines.append("## 需要修改的代码 (code)")
    for item in context["code"]:
        src = item["source"]
        lines.append(f"### {item['symbol']}  [{src['path']}:{src['start_line']}-{src['end_line']}]")
        lines.append(f"<!-- reason: {'; '.join(item['reason'])} -->")
        lines.append(_file_excerpt(context, item))
        lines.append("")
    lines.append("## 目标测试 (must pass after the change)")
    for item in context["tests"]["target"]:
        lines.append(f"- {item['node_id']} (covers {', '.join(item['covers'])})")
    lines.append("")
    lines.append("## 回归测试 (must keep passing)")
    for item in context["tests"]["regression"]:
        lines.append(f"- {item['node_id']} (covers {', '.join(item['covers']) or 'existing behaviour'})")
    return "\n".join(lines)


def _file_excerpt(context: dict[str, Any], item: dict[str, Any]) -> str:
    path = item["source"]["path"]
    # The caller injects the workspace through the settings used at build time;
    # the excerpt is filled by attach_excerpts().
    return context.get("_excerpts", {}).get(item["doc_id"], f"(see {path})")


def attach_excerpts(settings: Settings, context: dict[str, Any]) -> dict[str, Any]:
    """Attach real source snippets so the prompt and the report are self-contained."""

    excerpts: dict[str, str] = {}
    for item in context["code"]:
        lines = _read_lines(settings, item["source"]["path"])
        if lines is None:
            continue
        start = item["source"]["start_line"] - 1
        end = item["source"]["end_line"]
        numbered = [f"{index + 1:>4} | {line}" for index, line in enumerate(lines[start:end], start=start)]
        excerpts[item["doc_id"]] = "\n".join(numbered)
    context["_excerpts"] = excerpts
    return context
