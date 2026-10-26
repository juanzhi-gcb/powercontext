"""Import specifications, code symbols and tests into seekdb/OceanBase.

Every row keeps its real file path and line range so the context output can be
checked against the source tree. Re-importing a changed file bumps the row
``revision``; unchanged rows keep their revision.
"""

from __future__ import annotations

import ast
import hashlib
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database, dumps
from .terms import tokenize

try:  # PyYAML ships with the PowerContext runtime; keep a clear error otherwise.
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency guard
    yaml = None  # type: ignore[assignment]

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_SECTION_HEADING = re.compile(r"^##\s+(R\d+)\s*(.*)$")
_SPEC_MARKER = re.compile(r"""pytest\.mark\.spec\(\s*["']([^"']+)["']""")


@dataclass
class Doc:
    doc_id: str
    doc_type: str
    path: str
    symbol: str | None
    start_line: int
    end_line: int
    title: str
    content: str
    keywords: list[str] = field(default_factory=list)
    spec_ids: list[str] = field(default_factory=list)
    checksum: str = ""

    def finalize(self) -> Doc:
        self.checksum = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        return self


@dataclass
class IngestReport:
    run_id: str
    spec_docs: int
    code_docs: int
    test_docs: int
    links: int
    revisions_bumped: list[str]
    removed: list[str]
    source_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_docs": self.spec_docs,
            "code_docs": self.code_docs,
            "test_docs": self.test_docs,
            "links": self.links,
            "revisions_bumped": self.revisions_bumped,
            "removed": self.removed,
            "source_digest": self.source_digest,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_spec_file(settings: Settings, path: Path) -> list[Doc]:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    if match is None:
        raise ValueError(f"{path}: specification needs a YAML front matter block")
    if yaml is None:
        raise RuntimeError("PyYAML is required to read specification front matter")
    meta = yaml.safe_load(match.group(1)) or {}
    spec_id = str(meta.get("spec_id") or path.stem).strip()
    spec_title = str(meta.get("title") or spec_id).strip()
    keywords = [str(item) for item in (meta.get("keywords") or [])]
    anchors = [str(item) for item in (meta.get("anchors") or [])]

    rel = _relative(settings, path)
    lines = text.splitlines()
    body_start = text[: match.end()].count("\n") + 1

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for lineno in range(body_start, len(lines) + 1):
        line = lines[lineno - 1]
        heading = _SECTION_HEADING.match(line)
        if heading:
            if current is not None:
                current["end"] = lineno - 1
            current = {
                "key": heading.group(1),
                "heading": heading.group(2).strip(),
                "start": lineno,
                "body": [],
            }
            sections.append(current)
        elif current is not None:
            current["body"].append(line)

    docs: list[Doc] = []
    for section in sections:
        body_lines = _trim_blank(section["body"])
        if not body_lines:
            continue
        start = section["start"]
        end = start + len(body_lines)
        content = "\n".join(body_lines)
        item_id = f"{spec_id}#{section['key']}"
        docs.append(
            Doc(
                doc_id=f"spec:{item_id}",
                doc_type="spec",
                path=rel,
                symbol=item_id,
                start_line=start,
                end_line=end,
                title=f"{spec_title} {section['key']} {section['heading']}".strip(),
                content=content,
                keywords=keywords + [spec_id, section["key"], *anchors],
                spec_ids=[item_id],
            ).finalize()
        )
    return docs


def _trim_blank(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def extract_code_file(settings: Settings, path: Path) -> list[Doc]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{path}: cannot parse Python source: {exc}") from exc
    lines = source.splitlines()
    rel = _relative(settings, path)
    docs: list[Doc] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{prefix}{child.name}"
                decorators = [decorator.lineno for decorator in getattr(child, "decorator_list", [])]
                start = min(decorators + [child.lineno])
                end = getattr(child, "end_lineno", None) or child.lineno
                content = "\n".join(lines[start - 1 : end])
                docs.append(
                    Doc(
                        doc_id=f"code:{rel}::{qualified}",
                        doc_type="code",
                        path=rel,
                        symbol=qualified,
                        start_line=start,
                        end_line=end,
                        title=f"{qualified} ({_kind(child)})",
                        content=content,
                        keywords=[child.name, _kind(child)],
                    ).finalize()
                )
                walk(child, f"{qualified}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return docs


def _kind(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async-function"
    return "function"


def extract_test_file(settings: Settings, path: Path) -> list[Doc]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{path}: cannot parse test source: {exc}") from exc
    lines = source.splitlines()
    rel = _relative(settings, path)
    docs: list[Doc] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        decorator_text = "\n".join(
            ast.get_source_segment(source, decorator) or "" for decorator in node.decorator_list
        )
        spec_ids = _SPEC_MARKER.findall(decorator_text)
        is_regression = "pytest.mark.regression" in decorator_text
        start = min([decorator.lineno for decorator in node.decorator_list] + [node.lineno])
        end = getattr(node, "end_lineno", None) or node.lineno
        content = "\n".join(lines[start - 1 : end])
        docs.append(
            Doc(
                doc_id=f"test:{rel}::{node.name}",
                doc_type="test",
                path=rel,
                symbol=node.name,
                start_line=start,
                end_line=end,
                title=f"{path.stem}::{node.name}",
                content=content,
                keywords=list(spec_ids) + [node.name] + (["regression"] if is_regression else []),
                spec_ids=list(spec_ids),
            ).finalize()
        )
    return docs


def _relative(settings: Settings, path: Path) -> str:
    try:
        return path.resolve().relative_to(settings.workspace).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Link discovery
# ---------------------------------------------------------------------------


def _mentions(text: str, identifier: str) -> bool:
    if len(identifier) < 3:
        return False
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(identifier) + r"(?![A-Za-z0-9_])")
    return pattern.search(text) is not None


def _called_names(test_doc: Doc) -> set[str]:
    tree = ast.parse(test_doc.content)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Attribute):
                names.add(function.attr)
            elif isinstance(function, ast.Name):
                names.add(function.id)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def discover_links(spec_docs: list[Doc], code_docs: list[Doc], test_docs: list[Doc]) -> list[tuple[str, str, str]]:
    links: set[tuple[str, str, str]] = set()

    for spec in spec_docs:
        haystack = f"{spec.title}\n{spec.content}"
        for code in code_docs:
            short = (code.symbol or "").split(".")[-1]
            if _mentions(haystack, short) or _mentions(haystack, code.symbol or ""):
                links.add((spec.doc_id, code.doc_id, "spec-code"))

    code_by_short: dict[str, list[Doc]] = {}
    for code in code_docs:
        code_by_short.setdefault((code.symbol or "").split(".")[-1], []).append(code)

    for test in test_docs:
        for spec_id in test.spec_ids:
            links.add((test.doc_id, f"spec:{spec_id}", "test-spec"))
        for name in _called_names(test):
            for code in code_by_short.get(name, []):
                links.add((test.doc_id, code.doc_id, "test-code"))

    return sorted(links)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def ingest(settings: Settings, database: Database) -> IngestReport:
    spec_docs: list[Doc] = []
    for path in sorted(settings.specs_dir.glob("*.md")):
        spec_docs.extend(parse_spec_file(settings, path))

    code_docs: list[Doc] = []
    tests_dir = settings.demo_project / "tests"
    for path in sorted(settings.demo_project.rglob("*.py")):
        if "__pycache__" in path.parts or tests_dir in path.parents:
            continue
        code_docs.extend(extract_code_file(settings, path))

    test_docs: list[Doc] = []
    if tests_dir.is_dir():
        for path in sorted(tests_dir.glob("test_*.py")):
            test_docs.extend(extract_test_file(settings, path))

    all_docs = spec_docs + code_docs + test_docs
    if not all_docs:
        raise ValueError(f"nothing to ingest under {settings.workspace}")

    links = discover_links(spec_docs, code_docs, test_docs)
    digest = hashlib.sha256(
        "".join(sorted(f"{doc.doc_id}:{doc.checksum}" for doc in all_docs)).encode("utf-8")
    ).hexdigest()

    run_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    existing = {
        row["doc_id"]: row
        for row in database.query(
            "SELECT doc_id, checksum, revision FROM sdd_documents WHERE project_id = %s",
            (settings.project_id,),
        )
    }
    incoming_ids = {doc.doc_id for doc in all_docs}
    stale = sorted(set(existing) - incoming_ids)
    revisions_bumped: list[str] = []

    for doc in all_docs:
        previous = existing.get(doc.doc_id)
        if previous is None:
            database.execute(
                """
                INSERT INTO sdd_documents
                    (doc_id, project_id, doc_type, path, symbol, start_line, end_line,
                     title, content, keywords, checksum, revision, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    doc.doc_id, settings.project_id, doc.doc_type, doc.path, doc.symbol,
                    doc.start_line, doc.end_line, doc.title, doc.content,
                    dumps(doc.keywords), doc.checksum, 1, now,
                ),
            )
        elif previous["checksum"] != doc.checksum:
            database.execute(
                """
                UPDATE sdd_documents
                   SET doc_type=%s, path=%s, symbol=%s, start_line=%s, end_line=%s,
                       title=%s, content=%s, keywords=%s, checksum=%s,
                       revision=revision+1, updated_at=%s
                 WHERE doc_id=%s
                """,
                (
                    doc.doc_type, doc.path, doc.symbol, doc.start_line, doc.end_line,
                    doc.title, doc.content, dumps(doc.keywords), doc.checksum, now,
                    doc.doc_id,
                ),
            )
            revisions_bumped.append(doc.doc_id)
        else:
            database.execute(
                "UPDATE sdd_documents SET path=%s, start_line=%s, end_line=%s WHERE doc_id=%s",
                (doc.path, doc.start_line, doc.end_line, doc.doc_id),
            )

        _write_postings(database, doc)

    for doc_id in stale:
        database.execute("DELETE FROM sdd_postings WHERE doc_id = %s", (doc_id,))
        database.execute("DELETE FROM sdd_documents WHERE doc_id = %s", (doc_id,))

    database.execute(
        "DELETE FROM sdd_links WHERE src_id IN (SELECT doc_id FROM sdd_documents WHERE project_id = %s) "
        "OR dst_id IN (SELECT doc_id FROM sdd_documents WHERE project_id = %s)",
        (settings.project_id, settings.project_id),
    )
    for src, dst, kind in links:
        database.execute(
            "INSERT IGNORE INTO sdd_links (src_id, dst_id, kind) VALUES (%s,%s,%s)",
            (src, dst, kind),
        )

    database.execute(
        """
        INSERT INTO sdd_ingest_runs
            (run_id, project_id, started_at, finished_at, spec_docs, code_docs, test_docs, source_digest)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            run_id, settings.project_id, now, now, len(spec_docs), len(code_docs),
            len(test_docs), digest,
        ),
    )

    return IngestReport(
        run_id=run_id,
        spec_docs=len(spec_docs),
        code_docs=len(code_docs),
        test_docs=len(test_docs),
        links=len(links),
        revisions_bumped=sorted(revisions_bumped),
        removed=stale,
        source_digest=digest,
    )


def _write_postings(database: Database, doc: Doc) -> None:
    database.execute("DELETE FROM sdd_postings WHERE doc_id = %s", (doc.doc_id,))
    counts: Counter[str] = Counter()
    for term in tokenize(doc.title):
        counts[term] += 3.0
    for term in tokenize(" ".join(doc.keywords)):
        counts[term] += 5.0
    for term in tokenize(doc.content):
        counts[term] += 1.0
    rows = [(term, doc.doc_id, round(value, 4)) for term, value in counts.items()]
    if rows:
        database.executemany(
            "INSERT INTO sdd_postings (term, doc_id, tf) VALUES (%s,%s,%s)", rows
        )