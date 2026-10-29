#!/usr/bin/env python3
"""Build external archive records from ReScience C, FReD, and Retraction Watch.

This is a one-time importer. It writes qoder/examples/external-records.json,
which build-public-archive.py then merges into the browser corpus.

Example:
  python3 qoder/web/scripts/import-external-records.py \
    --rescience-dir /tmp/ReScience/articles \
    --fred-rds /tmp/fred/data.RDS \
    --retraction-csv /tmp/retraction_watch.csv

PyYAML is required for ReScience, and rdata for the FReD RDS snapshot.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
WEB = HERE.parents[1]
QODER = HERE.parents[2]
SERVER = QODER / "server"
sys.path.insert(0, str(SERVER))

RETRIEVED_AT = "2026-10-28"
TOTAL_TARGET = 215
RESCIENCE_TYPES = {
    "Replication",
    "Reproduction",
    "Reproduction / Ten Years Reproducibility Challenge",
}
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
CS_SUBJECT = re.compile(
    r"Computer Science|Data Science|Artificial Intelligence|Machine Learning|Software|Information Technology",
    re.I,
)
SCIENTIFIC_REASON = re.compile(
    r"Unreliable Results|Concerns/Issues about Data|Compromised Peer Review|"
    r"Concerns/Issues about Results|Paper Mill|Investigation by Third Party|"
    r"Falsification/Fabrication of Data|Duplication of/in Data",
    re.I,
)
LOW_VALUE_REASON = re.compile(
    r"Plagiarism of Text|Euphemisms for Plagiarism|Computer-Aided Content|"
    r"Lack of Approval|Notice - Limited or No Information",
    re.I,
)
RESULT_MARKER = re.compile(r"^\s*\[[^\]]{1,40}\]\s*")


def compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def truncate(value: object, limit: int) -> str:
    text = compact(value)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def clean_abstract(value: object) -> str:
    text = compact(value)
    text = re.sub(r"\\cite\{[^}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = text.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_")
    text = text.replace('\\"', '"').replace("``", '"').replace("''", '"')
    return compact(text)


def parse_date(value: object) -> str:
    text = compact(value)
    if not text:
        return ""
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}T00:00:00Z"
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        month, day, year = (int(part) for part in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
    match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if match and match.group(1).lower() in MONTHS:
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
    match = re.search(r"\b(\d{4})\b", text)
    if match:
        return f"{match.group(1)}-01-01T00:00:00Z"
    return ""


def year_iso(value: object, fallback: str) -> str:
    text = compact(value)
    try:
        year = int(float(text))
    except (TypeError, ValueError):
        return fallback
    if year < 1900 or year > 2100:
        return fallback
    return f"{year:04d}-01-01T00:00:00Z"


def doi_locator(value: object) -> str:
    doi = compact(value)
    if not doi or doi.lower() in {"unavailable", "0", "nan", "none"}:
        return ""
    if doi.startswith("http://") or doi.startswith("https://"):
        return doi
    return "https://doi.org/" + doi


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", compact(value).lower()).strip("-") or "record"


def normalize_title(value: object) -> str:
    text = compact(value).lower()
    text = re.sub(r"^\[[^\]]{1,12}\]\s*", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def unique_terms(values: list[object], limit: int = 90) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        text = truncate(value, 140)
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        terms.append(text)
        if len(terms) >= limit:
            break
    return terms


def source_keys() -> tuple[set[str], set[str]]:
    path = WEB / "src" / "public-archive.json"
    if not path.exists():
        return set(), set()
    corpus = json.loads(path.read_text(encoding="utf-8"))
    records = [record for record in corpus.get("records", []) if not record.get("source")]
    titles = {normalize_title(record.get("title", "")) for record in records}
    dois: set[str] = set()
    for record in records:
        for evidence in record.get("evidence", []):
            match = re.search(r"10\.\d{4,9}/[^\s\"<>]+", evidence.get("locator", ""))
            if match:
                dois.add(match.group(0).lower().rstrip(".,;)"))
    return titles, dois


def get_value(items: object, key: str) -> str:
    if not isinstance(items, list):
        return ""
    for item in items:
        if isinstance(item, dict) and item.get(key):
            return compact(item[key])
    return ""


def rescience_records(
    directory: Path,
    limit: int,
    existing_titles: set[str],
    existing_dois: set[str],
) -> list[dict]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required to import ReScience metadata.") from exc

    candidates: dict[str, tuple[tuple, dict]] = {}
    for path in sorted(directory.glob("**/article.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or compact(data.get("type")) not in RESCIENCE_TYPES:
            continue
        article_doi = get_value(data.get("article"), "doi")
        article_url = get_value(data.get("article"), "url")
        title = compact(data.get("title"))
        abstract = clean_abstract(data.get("abstract"))
        if not title or not article_doi:
            continue
        record_key = article_doi.lower()
        published = ""
        for item in data.get("dates") or []:
            if isinstance(item, dict) and item.get("published"):
                published = parse_date(item["published"])
                break
        replication = data.get("replication") or []
        rep_cite = rep_url = rep_doi = ""
        for item in replication:
            if not isinstance(item, dict):
                continue
            rep_cite = rep_cite or compact(item.get("cite"))
            rep_url = rep_url or compact(item.get("url"))
            rep_doi = rep_doi or compact(item.get("doi"))
        score = (bool(abstract), len(abstract), published)
        if record_key not in candidates or score > candidates[record_key][0]:
            candidates[record_key] = (
                score,
                {
                    "title": title,
                    "abstract": abstract,
                    "article_doi": article_doi,
                    "article_url": article_url,
                    "published": published or "2020-01-01T00:00:00Z",
                    "rep_cite": rep_cite,
                    "rep_url": rep_url,
                    "rep_doi": rep_doi,
                    "keywords": compact(data.get("keywords")),
                    "language": compact(data.get("language")),
                    "domain": compact(data.get("domain")),
                    "code_url": get_value(data.get("code"), "url"),
                    "code_doi": get_value(data.get("code"), "doi"),
                    "data_url": get_value(data.get("data"), "url"),
                    "data_doi": get_value(data.get("data"), "doi"),
                },
            )

    ordered = sorted(candidates.values(), key=lambda item: item[0], reverse=True)
    records: list[dict] = []
    used_ids: set[str] = set()
    for _, item in ordered:
        if len(records) >= limit:
            break
        if item["article_doi"].lower() in existing_dois:
            continue
        if normalize_title(item["title"]) in existing_titles:
            continue
        if normalize_title(RESULT_MARKER.sub("", item["title"])) in existing_titles:
            continue
        abstract = item["abstract"]
        raw_title = item["title"]
        lowered = raw_title.lower()
        if "¬" in raw_title[:10] or "\\sim" in raw_title[:16] or lowered.startswith("[~"):
            outcome = "failed"
        elif re.search(r"partly successful|partially successful|mixed result", abstract, re.I):
            outcome = "mixed"
        else:
            outcome = "successful"
        title = RESULT_MARKER.sub("", raw_title).strip() or raw_title
        idea = abstract or f"Replication of: {item['rep_cite'] or title}"
        mechanism = abstract or (
            "External replication record; the source metadata does not provide an abstract. "
            f"Replication of: {item['rep_cite'] or title}"
        )
        if outcome == "failed":
            failure = "Observed negative replication outcome. " + truncate(abstract, 700)
            stance = "refutes"
        elif outcome == "mixed":
            failure = "Mixed replication outcome. " + truncate(abstract, 700)
            stance = "limits"
        else:
            failure = "External replication record; the source reports a successful replication."
            stance = "supports"
        record_id = "ext-rescience-" + slug(item["article_doi"])
        if record_id in used_ids:
            continue
        used_ids.add(record_id)
        locator = doi_locator(item["article_doi"]) or item["article_url"]
        evidence = [
            {
                "id": record_id + "-article",
                "source_type": "paper",
                "title": title,
                "locator": locator,
                "excerpt": truncate(abstract or mechanism, 1400),
                "stance": stance,
                "published_at": item["published"],
            }
        ]
        code_locator = item["code_url"] or doi_locator(item["code_doi"])
        if code_locator:
            evidence.append(
                {
                    "id": record_id + "-code",
                    "source_type": "code",
                    "title": "Replication code",
                    "locator": code_locator,
                    "excerpt": "Code archive referenced by the replication article.",
                    "stance": "supports",
                    "published_at": item["published"],
                }
            )
        data_locator = item["data_url"] or doi_locator(item["data_doi"])
        if data_locator:
            evidence.append(
                {
                    "id": record_id + "-data",
                    "source_type": "dataset",
                    "title": "Replication data",
                    "locator": data_locator,
                    "excerpt": "Data archive referenced by the replication article.",
                    "stance": "supports",
                    "published_at": item["published"],
                }
            )
        terms = [
            title,
            item["rep_cite"],
            item["domain"],
            item["language"],
            *item["keywords"].split(","),
            "replication",
            "reproducibility",
            "复现",
            "复现失败" if outcome == "failed" else "复现成功" if outcome == "successful" else "复现结果混合",
            "可重复性",
            "重复实验",
        ]
        records.append(
            {
                "id": record_id,
                "title": title,
                "idea": idea,
                "mechanism": mechanism,
                "failure_condition": failure,
                "task": "replication-studies",
                "domain": "replication-studies",
                "assumptions": [],
                "search_terms": unique_terms(terms),
                "historical_decision": None,
                "available_at": item["published"],
                "evidence": evidence,
                "record_type": "replication",
                "source": "rescience-c",
                "source_url": "https://github.com/ReScience/articles",
                "license": "CC BY 4.0",
                "retrieved_at": RETRIEVED_AT,
                "original_doi": item["rep_doi"] or None,
                "replication_doi": item["article_doi"],
                "outcome": outcome,
                "outcome_quote": truncate(abstract or mechanism, 1400),
                "discipline_raw": item["domain"] or None,
            }
        )
    return records


def fred_records(
    rds_path: Path,
    limit: int,
    existing_titles: set[str],
    existing_dois: set[str],
) -> list[dict]:
    try:
        import rdata
        import warnings
    except ImportError as exc:
        raise SystemExit("rdata is required to read the FReD RDS snapshot.") from exc

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame = rdata.conversion.convert(rdata.parser.parse_file(str(rds_path)))
    grouped: dict[str, tuple[tuple, dict]] = {}
    for row in frame.to_dict("records"):
        def text(key: str) -> str:
            return compact(row.get(key))

        reported = text("reported_success")
        if reported not in {"failed", "mixed"}:
            continue
        quote = text("reported_success_quote")
        if len(quote) < 120:
            continue
        title_o = text("title_o")
        title_r = text("title_r")
        doi_o = text("doi_o")
        doi_r = text("doi_r")
        if not title_o or not (doi_o or doi_r):
            continue
        if doi_o.lower() in existing_dois or normalize_title(title_o) in existing_titles:
            continue
        if title_r and normalize_title(title_r) in existing_titles:
            continue
        key = text("fred_id") or text("entry_id") or doi_o
        score = (
            reported == "failed",
            len(quote),
            bool(doi_r),
            len(text("description")),
            text("year_r"),
        )
        if key not in grouped or score > grouped[key][0]:
            grouped[key] = (
                score,
                {
                    "fred_id": key,
                    "title_o": title_o,
                    "title_r": title_r,
                    "doi_o": doi_o,
                    "doi_r": doi_r,
                    "url_r": text("url_r"),
                    "claim": text("claim_text_o"),
                    "description": text("description"),
                    "study_r": text("study_r"),
                    "quote": re.sub(r"^[\s\"'“”‘’.;:]+", "", quote),
                    "outcome": reported,
                    "discipline": text("discipline"),
                    "tags": text("tags"),
                    "year_o": text("year_o"),
                    "year_r": text("year_r"),
                },
            )

    per_doi: dict[str, tuple[tuple, dict]] = {}
    for score, item in grouped.values():
        key = item["doi_o"].lower() or normalize_title(item["title_o"])
        if key not in per_doi or score > per_doi[key][0]:
            per_doi[key] = (score, item)

    by_discipline: dict[str, list[tuple[tuple, dict]]] = defaultdict(list)
    for score, item in per_doi.values():
        by_discipline[item["discipline"] or "Unspecified"].append((score, item))
    for rows in by_discipline.values():
        rows.sort(key=lambda entry: entry[0], reverse=True)
    selected: list[dict] = []
    while len(selected) < limit and any(by_discipline.values()):
        for discipline in sorted(by_discipline):
            if not by_discipline[discipline]:
                continue
            selected.append(by_discipline[discipline].pop(0)[1])
            if len(selected) == limit:
                break

    records: list[dict] = []
    used_ids: set[str] = set()
    for item in selected:
        record_id = "ext-fred-" + slug(item["fred_id"])
        if record_id in used_ids:
            continue
        used_ids.add(record_id)
        title = f"Replication of: {item['title_o']}"
        idea = item["claim"] or item["title_o"]
        if len(item["description"]) >= 30 and not re.match(r"^\d", item["description"]):
            mechanism = item["description"]
        elif len(item["study_r"]) >= 30:
            mechanism = item["study_r"]
        else:
            mechanism = f"Replication testing the claim: {item['title_o']}"
        available_at = year_iso(item["year_r"], "2026-02-01T00:00:00Z")
        original_at = year_iso(item["year_o"], available_at)
        rep_at = year_iso(item["year_r"], available_at)
        if item["outcome"] == "failed":
            failure = "Observed replication failure: " + truncate(item["quote"], 1000)
            stance = "refutes"
        else:
            failure = "Mixed replication outcome: " + truncate(item["quote"], 1000)
            stance = "limits"
        evidence: list[dict] = []
        original_locator = doi_locator(item["doi_o"])
        if original_locator:
            evidence.append(
                {
                    "id": record_id + "-original",
                    "source_type": "paper",
                    "title": "Original study: " + item["title_o"],
                    "locator": original_locator,
                    "excerpt": truncate(item["claim"] or item["title_o"], 1000),
                    "stance": "supports",
                    "published_at": original_at,
                }
            )
        replication_locator = doi_locator(item["doi_r"]) or item["url_r"]
        if replication_locator:
            evidence.append(
                {
                    "id": record_id + "-replication",
                    "source_type": "paper",
                    "title": "Replication: " + (item["title_r"] or ("of " + item["title_o"])),
                    "locator": replication_locator,
                    "excerpt": truncate(item["quote"], 1400),
                    "stance": stance,
                    "published_at": rep_at,
                }
            )
        if not evidence:
            continue
        terms = [
            item["title_o"],
            item["title_r"],
            item["claim"],
            item["discipline"],
            item["tags"],
            "replication",
            "failed replication" if item["outcome"] == "failed" else "mixed replication",
            "复现",
            "复现失败" if item["outcome"] == "failed" else "复现结果混合",
            "可重复性",
            "重复实验",
        ]
        records.append(
            {
                "id": record_id,
                "title": title,
                "idea": idea,
                "mechanism": mechanism,
                "failure_condition": failure,
                "task": "replication-studies",
                "domain": "replication-studies",
                "assumptions": [],
                "search_terms": unique_terms(terms),
                "historical_decision": None,
                "available_at": available_at,
                "evidence": evidence,
                "record_type": "replication",
                "source": "fred",
                "source_url": "https://github.com/forrtproject/FReD",
                "license": "Package MIT; data license not declared",
                "retrieved_at": RETRIEVED_AT,
                "original_doi": item["doi_o"] or None,
                "replication_doi": item["doi_r"] or None,
                "outcome": item["outcome"],
                "outcome_quote": truncate(item["quote"], 1400),
                "discipline_raw": item["discipline"] or None,
            }
        )
        if len(records) >= limit:
            break
    return records


def retraction_records(
    csv_path: Path,
    limit: int,
    existing_titles: set[str],
    existing_dois: set[str],
) -> list[dict]:
    candidates: list[tuple[tuple, dict]] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            title = compact(row.get("Title"))
            subject = compact(row.get("Subject"))
            reason = re.sub(r"[;\s]+$", "", compact(row.get("Reason")))
            reason = re.sub(r";\s*", "; ", reason)
            notes = compact(row.get("Notes"))
            original_doi = compact(row.get("OriginalPaperDOI"))
            notice_doi = compact(row.get("RetractionDOI"))
            nature = compact(row.get("RetractionNature"))
            if nature != "Retraction" or not title or not original_doi:
                continue
            if original_doi.lower() in {"unavailable", "0", "nan"}:
                continue
            if not CS_SUBJECT.search(subject) or not SCIENTIFIC_REASON.search(reason):
                continue
            if re.search(r"Notice - Limited or No Information", reason) and not notes:
                continue
            if LOW_VALUE_REASON.fullmatch(reason):
                continue
            published_at = parse_date(row.get("RetractionDate")) or parse_date(row.get("OriginalPaperDate"))
            if not published_at or published_at < "2015-01-01":
                continue
            if original_doi.lower() in existing_dois or normalize_title(title) in existing_titles:
                continue
            score = 0
            if re.search(r"Unreliable Results|Concerns/Issues about Results|Concerns/Issues about Data|Falsification|Duplication of/in Data", reason, re.I):
                score += 4
            if re.search(r"Compromised Peer Review|Paper Mill|Investigation by Third Party", reason, re.I):
                score += 3
            if re.search(r"Investigation by Journal/Publisher", reason, re.I):
                score += 2
            if LOW_VALUE_REASON.search(reason):
                score -= 3
            if notes:
                score += 1
            candidates.append(
                (
                    (score, published_at, len(notes)),
                    {
                        "record_id": compact(row.get("Record ID")),
                        "title": title,
                        "subject": subject,
                        "reason": reason,
                        "notes": notes,
                        "journal": compact(row.get("Journal")),
                        "publisher": compact(row.get("Publisher")),
                        "original_doi": original_doi,
                        "notice_doi": notice_doi,
                        "published_at": published_at,
                        "original_date": parse_date(row.get("OriginalPaperDate")) or published_at,
                    },
                )
            )
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    records: list[dict] = []
    used_dois: set[str] = set()
    used_ids: set[str] = set()
    for _, item in candidates:
        doi_key = item["original_doi"].lower()
        if doi_key in used_dois:
            continue
        used_dois.add(doi_key)
        record_id = "ext-retraction-" + slug(item["record_id"] or item["original_doi"])
        if record_id in used_ids:
            continue
        used_ids.add(record_id)
        detail = item["reason"].rstrip(".") + (". " + item["notes"] if item["notes"] else ".")
        idea = f"Retracted paper: {item['title']}. Reason: {item['reason']}."
        mechanism = (
            "External retraction record; no mechanism claim is asserted. "
            f"The published paper was retracted for: {item['reason']}."
        )
        failure = "Retraction reason: " + detail
        evidence: list[dict] = []
        notice_locator = doi_locator(item["notice_doi"])
        if notice_locator:
            evidence.append(
                {
                    "id": record_id + "-notice",
                    "source_type": "retraction_notice",
                    "title": "Retraction notice: " + item["title"],
                    "locator": notice_locator,
                    "excerpt": truncate(detail, 1400),
                    "stance": "supports",
                    "published_at": item["published_at"],
                }
            )
        original_locator = doi_locator(item["original_doi"])
        if original_locator:
            evidence.append(
                {
                    "id": record_id + "-original",
                    "source_type": "paper",
                    "title": "Retracted paper: " + item["title"],
                    "locator": original_locator,
                    "excerpt": "Original paper record; retracted by the notice.",
                    "stance": "refutes",
                    "published_at": item["original_date"],
                }
            )
        if not evidence:
            continue
        terms = [
            item["title"],
            item["subject"],
            item["reason"],
            item["journal"],
            item["publisher"],
            "retraction",
            "retracted paper",
            "research integrity",
            "撤稿",
            "学术不端",
            "数据问题",
            "结果不可靠",
        ]
        records.append(
            {
                "id": record_id,
                "title": item["title"],
                "idea": idea,
                "mechanism": mechanism,
                "failure_condition": failure,
                "task": "research-integrity",
                "domain": "research-integrity",
                "assumptions": [],
                "search_terms": unique_terms(terms),
                "historical_decision": None,
                "available_at": item["published_at"],
                "evidence": evidence,
                "record_type": "retraction",
                "source": "retraction-watch",
                "source_url": "https://gitlab.com/crossref/retraction-watch-data",
                "license": "No license file; public Crossref/Retraction Watch data",
                "retrieved_at": RETRIEVED_AT,
                "original_doi": item["original_doi"],
                "replication_doi": None,
                "outcome": "retracted",
                "outcome_quote": truncate(detail, 1400),
                "discipline_raw": item["subject"],
            }
        )
        if len(records) >= limit:
            break
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rescience-dir", type=Path, required=True)
    parser.add_argument("--fred-rds", type=Path, required=True)
    parser.add_argument("--retraction-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=QODER / "examples" / "external-records.json")
    parser.add_argument("--total", type=int, default=TOTAL_TARGET)
    parser.add_argument("--rescience-limit", type=int, default=40)
    parser.add_argument("--retraction-limit", type=int, default=50)
    args = parser.parse_args()

    existing_titles, existing_dois = source_keys()
    rescience = rescience_records(args.rescience_dir, args.rescience_limit, existing_titles, existing_dois)
    retractions = retraction_records(args.retraction_csv, args.retraction_limit, existing_titles, existing_dois)
    fred_limit = max(0, args.total - len(rescience) - len(retractions))
    fred = fred_records(args.fred_rds, fred_limit, existing_titles, existing_dois)
    records = [*rescience, *fred, *retractions]
    if len(records) != args.total:
        raise SystemExit(f"Expected {args.total} records, built {len(records)}")

    sources = [
        {
            "id": "rescience-c",
            "name": "ReScience C",
            "url": "https://github.com/ReScience/articles",
            "license": "CC BY 4.0 (article-level)",
            "retrieved_at": RETRIEVED_AT,
            "records": len(rescience),
            "note": "Replication and reproduction articles with abstracts; editorials and letters excluded.",
        },
        {
            "id": "fred",
            "name": "FORRT Replication Database (FReD)",
            "url": "https://github.com/forrtproject/FReD",
            "license": "R package MIT; data license not declared",
            "retrieved_at": RETRIEVED_AT,
            "records": len(fred),
            "note": "Failed or mixed replications with a reported-outcome quote; one row per fred_id.",
        },
        {
            "id": "retraction-watch",
            "name": "Retraction Watch",
            "url": "https://gitlab.com/crossref/retraction-watch-data",
            "license": "No license file; public Crossref/Retraction Watch data",
            "retrieved_at": RETRIEVED_AT,
            "records": len(retractions),
            "note": "Computer-science/data-science retractions with a DOI and a scientific reason.",
        },
    ]
    output = {
        "version": "external-2026-10-28.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "total": len(records),
                "rescience": len(rescience),
                "fred": len(fred),
                "retractions": len(retractions),
                "with_evidence": sum(1 for record in records if record["evidence"]),
                "bytes": args.output.stat().st_size,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
