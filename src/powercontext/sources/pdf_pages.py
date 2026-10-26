# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Page-level Sources for complete offline PDF documents."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from itertools import combinations
from typing import TYPE_CHECKING
from urllib.parse import quote

from pydantic import BaseModel

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.definitions import SourceDefinition
from powercontext.sources.models import Source, SourceMaterialization

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from powercontext.artifacts import MemoryCitation
    from powercontext.builtin.artifacts.memory.models import MemoryHit

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_DEFINITION_VERSION = "1"
_SOURCE_ID_PREFIX = "pdf"
_TERM_PATTERN = re.compile(r"[a-z]+|\d+")
_ACRONYM_PATTERN = re.compile(r"\b(?:r&d|d&a|sg&a|sga)\b")
_STATEMENT_PATTERNS = {
    "income": re.compile(r"statements?\s+of\s+(?:income|operations|earnings)"),
    "balance": re.compile(r"balance\s+sheets?|statements?\s+of\s+financial\s+position"),
    "cash": re.compile(r"statements?\s+of\s+cash\s+flows?"),
    "segment": re.compile(r"by business segment|segment information|segment data"),
}
_AFFINITY_KEYWORDS = {
    "balance": frozenset(
        {"liability", "liabilities", "asset", "assets", "balance", "sheet", "debt", "liquidity", "quick",
         "current", "working", "borrowings", "capital", "intensive", "property", "plant", "equipment",
         "payable", "payables", "receivable", "receivables", "inventory"}
    ),
    "cash": frozenset(
        {"cash", "capex", "capital", "expenditure", "expenditures", "dividend", "dividends", "flow", "flows",
         "buyback", "repurchase"}
    ),
    "income": frozenset(
        {"income", "revenue", "revenues", "sales", "margin", "margins", "profit", "profits", "ebitda",
         "operating", "earnings", "tax", "expense", "expenses", "cost", "costs", "eps", "diluted", "cogs",
         "inventory", "growth"}
    ),
    "segment": frozenset({"segment", "segments", "division", "divisions"}),
}
_AFFINITY_BONUS = 0.8
_ACRONYMS = {
    "r&d": "research development",
    "d&a": "depreciation amortization",
    "sg&a": "selling general administrative",
    "sga": "selling general administrative",
}
_STOPWORDS = frozenset(
    {
        "a", "about", "after", "all", "also", "an", "and", "any", "are", "as", "at", "be", "because",
        "been", "before", "between", "both", "by", "can", "did", "do", "does", "during", "each", "for",
        "from", "had", "has", "have", "how", "if", "in", "into", "is", "it", "its", "just", "more",
        "most", "no", "not", "of", "on", "or", "other", "our", "out", "over", "per", "such", "than",
        "that", "the", "their", "then", "there", "these", "they", "this", "those", "to", "under", "up",
        "was", "we", "were", "what", "when", "where", "which", "while", "who", "why", "will", "with",
        "would", "year", "years",
    }
)
_MAX_QUERY_TERMS = 8
_HITS_PER_QUERY = 100
_MAX_CANDIDATES = 200
_HEADING_CHARS = 300
_DOCUMENT_BOOST = 2.0
_SCOPED_WEIGHT = 1.0
_SCOPED_TERMS = 6
_DOMINANCE_RATIO = 1.5
_RRF_OFFSET = 60
_RRF_WEIGHT = 0.6
_SINGLE_TERM_WEIGHT = 0.5
_SYNONYM_WEIGHT = 0.3

# Financial-report questions rarely repeat the filing's own vocabulary: a question about
# "geographies" is answered by a page that lists countries and businesses. Expanding a few
# leading terms with their filing vocabulary keeps lexical retrieval usable without a model.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "geographies": ("geographic", "regions", "countries", "markets", "segments"),
    "geography": ("geographic", "regions", "countries", "markets", "segments"),
    "operates": ("businesses", "segments", "operations"),
    "operating": ("operations", "income"),
    "legal": ("litigation", "proceedings", "claims", "regulatory", "matters"),
    "battles": ("litigation", "proceedings", "claims", "disputes"),
    "lawsuit": ("litigation", "proceedings", "claims"),
    "litigation": ("proceedings", "claims", "regulatory"),
    "revenue": ("sales", "net"),
    "sales": ("revenue", "net"),
    "capex": ("capital", "expenditures", "property"),
    "ebitda": ("operating", "income", "depreciation", "amortization"),
    "margin": ("profit", "income", "sales"),
    "restructuring": ("charges", "severance", "productivity"),
    "employees": ("workforce", "personnel"),
    "debt": ("borrowings", "notes", "obligations"),
    "dividends": ("payout", "repurchase"),
    "risk": ("uncertainties", "factors"),
    "liquidity": ("cash", "assets", "liabilities", "current", "receivables"),
    "quick": ("cash", "receivables", "current", "assets"),
    "ratio": ("assets", "liabilities", "current"),
    "cyclicality": ("cyclical", "cycle", "economic"),
    "categories": ("segment", "segments", "products", "services"),
    "customers": ("customer", "clients"),
    "concentration": ("customers", "percent"),
    "acquisitions": ("acquired", "divestitures", "transaction"),
    "climate": ("environmental", "emissions", "sustainability"),
}


class PDFDocumentInput(BaseModel):
    """One complete PDF file and the caller-stable identity of that document."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page with its extractable text."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """A captured page addressed by document identity, file digest and physical page."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str

    @property
    def source_id(self) -> str:
        return self.name


def parse_pdf_document(value: PDFDocumentInput, /) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of the original PDF, in order, starting at page 1."""

    document_id = value.document_id
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must be a non-empty string")  # noqa: TRY003
    if not value.content:
        raise ValueError("PDF content must not be empty")  # noqa: TRY003
    document_sha256 = hashlib.sha256(value.content).hexdigest()
    from pypdf import PdfReader  # imported here so the module stays importable without pypdf

    try:
        reader = PdfReader(io.BytesIO(value.content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a non-empty password")  # noqa: TRY003
        pages = tuple(
            PDFPageInput(
                document_id=document_id,
                document_sha256=document_sha256,
                page_number=number,
                text=page.extract_text() or "",
            )
            for number, page in enumerate(reader.pages, start=1)
        )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF content could not be parsed") from error  # noqa: TRY003
    if not pages:
        raise ValueError("PDF content must contain at least one page")  # noqa: TRY003
    return pages


async def search_pdf_pages(
    memory: object,
    question: str,
    /,
    limit: int = 10,
) -> tuple[MemoryCitation, ...]:
    """Return distinct page citations for one natural-language question."""

    if limit < 1:
        raise ValueError("limit must be positive")  # noqa: TRY003
    terms = _question_terms(question)
    if not terms:
        return ()
    expanded = _expand_terms(terms)
    from powercontext.artifacts import MemoryCitation as Citation
    from powercontext.builtin.runtime.models import GetMemoryEntryRequest, SearchMemoryRequest

    scored: dict[tuple[str, str, str], tuple[MemoryHit, float]] = {}

    async def collect(probe: str, weight: float) -> None:
        page = await memory.search(  # type: ignore[attr-defined]
            SearchMemoryRequest(query=probe, mode="fts", limit=_HITS_PER_QUERY)
        )
        for rank, hit in enumerate(page.hits, start=1):
            identifier = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            current = scored.get(identifier)
            contribution = weight / (_RRF_OFFSET + rank)
            if current is None:
                scored[identifier] = (hit, contribution)
            else:
                scored[identifier] = (current[0], current[1] + contribution)

    for subquery, weight in _subqueries(terms, expanded, question):
        await collect(subquery, weight)

    if not scored:
        return ()
    target = _target_document(question, tuple(hit for hit, _ in scored.values()))
    if target is None:
        target = _dominant_document(scored)
    if target is not None:
        document_term = re.sub(r"[^a-z0-9]", "", target.split("_")[0].casefold())
        for term in terms[:6]:
            await collect(f"{document_term} {term}", _SCOPED_WEIGHT)
        for synonym in expanded[:_SCOPED_TERMS]:
            if synonym in terms:
                continue
            await collect(f"{document_term} {synonym}", _SYNONYM_WEIGHT)

    hits = tuple(hit for hit, _ in scored.values())
    fused = tuple(contribution for _, contribution in scored.values())
    lexical = _rank_scores(expanded, tuple(hit.text for hit in hits), _affinity_hints(terms))
    scores = [
        lexical[index] / max(lexical) + _RRF_WEIGHT * fused[index] / max(fused)
        for index in range(len(hits))
    ]
    if target is not None:
        for index, hit in enumerate(hits):
            if _document_of(hit) == target:
                scores[index] *= _DOCUMENT_BOOST
    ranked = sorted(
        zip(scores, hits, strict=True),
        key=lambda pair: (-pair[0], pair[1].entry_id),
    )[:_MAX_CANDIDATES]
    ordered = [hit for _score, hit in ranked]
    citations: list[MemoryCitation] = []
    seen_pages: set[str] = set()
    for hit in ordered:
        citation = Citation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry  # type: ignore[attr-defined]
        page_ids = [reference.source_id for reference in entry.sources]
        if not page_ids or any(page_id in seen_pages for page_id in page_ids):
            continue
        seen_pages.update(page_ids)
        citations.append(citation)
        if len(citations) >= limit:
            break
    return tuple(citations)


class PDFPageSourceAdapter:
    """Resolve and read one captured PDF page."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        return PDFPageSource(
            name=_page_source_id(value.document_id, value.document_sha256, value.page_number),
            definition_version=PDF_PAGE_DEFINITION_VERSION,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one captured page as the standard text-evidence projection."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_ADAPTER = PDFPageSourceAdapter()
PDF_PAGE_TEXT_EVIDENCE_PROJECTION = PDFPageTextEvidenceProjection()
PDF_PAGE_SOURCE_DEFINITION: SourceDefinition[PDFPageInput, PDFPageSource, PDFPageInput] = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    version=PDF_PAGE_DEFINITION_VERSION,
    projections=(PDF_PAGE_TEXT_EVIDENCE_PROJECTION,),
)


def _page_source_id(document_id: str, document_sha256: str, page_number: int, /) -> str:
    source_id = f"{_SOURCE_ID_PREFIX}:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("PDF page source identity exceeds the supported length")  # noqa: TRY003
    return source_id


def _question_terms(question: str, /) -> tuple[str, ...]:
    normalized = _ACRONYM_PATTERN.sub(lambda match: _ACRONYMS[match.group(0)], question.lower())
    terms: list[str] = []
    for term in _TERM_PATTERN.findall(normalized):
        if term in _STOPWORDS or len(term) < 2 or term in terms:
            continue
        terms.append(term)
    return tuple(terms)


def _variants(term: str, /) -> tuple[str, ...]:
    """Return only the inflections that can plausibly be a real word."""

    if not term.isalpha() or len(term) < 4:
        return (term,)
    if term.endswith(("ly", "ed", "ing", "ous", "ive", "al", "ic", "ss")):
        return (term,)
    forms = {term}
    if term.endswith("ies"):
        forms.add(term[:-3] + "y")
    elif term.endswith("y"):
        forms.add(term[:-1] + "ies")
    elif term.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(term + "es")
    else:
        forms.add(term + "s")
    if term.endswith("s") and not term.endswith("ss"):
        forms.add(term[:-1])
    return tuple(forms)


def _expand_terms(terms: tuple[str, ...], /) -> tuple[str, ...]:
    expanded = list(terms)
    for term in terms[:6]:
        for synonym in _EXPANSIONS.get(term, ()):
            if synonym not in expanded:
                expanded.append(synonym)
    for term in terms[:6]:
        for form in _variants(term):
            if form not in expanded:
                expanded.append(form)
    return tuple(expanded)


def _subqueries(
    terms: tuple[str, ...],
    expanded: tuple[str, ...],
    question: str,
    /,
) -> tuple[tuple[str, float], ...]:
    """Return short probes with the weight each earned in the fused ranking."""

    focused = terms[:_MAX_QUERY_TERMS]
    queries: list[tuple[str, float]] = [(" ".join(pair), 1.0) for pair in combinations(focused, 2)]
    queries.extend((term, _SINGLE_TERM_WEIGHT) for term in focused)
    queries.extend((term, _SYNONYM_WEIGHT) for term in expanded if term not in terms)
    queries.append((question, 1.0))
    return tuple(queries)


def _document_of(hit: MemoryHit, /) -> str:
    """The document identity every page entry carries on its first line."""

    return hit.text.split("\n", 1)[0].strip()


def _target_document(question: str, hits: tuple[MemoryHit, ...], /) -> str | None:
    """Name the one document a question is about, when it says so unambiguously.

    A scope may hold several filings, so pages from other companies compete for the same
    generic terms; the asked-about document is the only disambiguator available offline.
    """

    documents = {_document_of(hit) for hit in hits}
    compact = re.sub(r"[^a-z0-9]", "", question.casefold())
    matches = []
    for name in documents:
        head = re.sub(r"[^a-z0-9]", "", name.split("_")[0].casefold())
        if len(head) >= 3 and head in compact:
            matches.append(name)
    return matches[0] if len(matches) == 1 else None


def _dominant_document(scored: dict[tuple[str, str, str], tuple[MemoryHit, float]], /) -> str | None:
    """Fall back to the document that owns most of the first-pass evidence."""

    mass: dict[str, float] = {}
    for hit, contribution in scored.values():
        document = _document_of(hit)
        mass[document] = mass.get(document, 0.0) + contribution
    ranked = sorted(mass.items(), key=lambda item: -item[1])
    if not ranked:
        return None
    if len(ranked) == 1:
        return ranked[0][0]
    return ranked[0][0] if ranked[0][1] >= _DOMINANCE_RATIO * ranked[1][1] else None


def _affinity_hints(terms: tuple[str, ...], /) -> tuple[re.Pattern[str], ...]:
    """Map the metrics a question names onto the statement that reports them."""

    lowered = {term.casefold() for term in terms}
    return tuple(
        _STATEMENT_PATTERNS[kind]
        for kind, keywords in _AFFINITY_KEYWORDS.items()
        if lowered & keywords
    )


def _rank_scores(
    terms: tuple[str, ...],
    texts: tuple[str, ...],
    hints: tuple[re.Pattern[str], ...] = (),
    /,
) -> list[float]:
    """Rank pages by BM25 plus heading position and rare-term presence.

    Financial reports carry the section title at the top of a page, so a query term in the
    leading text is stronger evidence than the same term deep inside a table.
    """

    token_lists = [_TERM_PATTERN.findall(text.lower()) for text in texts]
    total = len(token_lists)
    if not total:
        return []
    average_length = sum(len(tokens) for tokens in token_lists) / total
    wanted = set(terms)
    document_frequency: dict[str, int] = {}
    for tokens in token_lists:
        for term in wanted.intersection(tokens):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    idf = {
        term: math.log(1 + (total - document_frequency.get(term, 0) + 0.5) / (document_frequency.get(term, 0) + 0.5))
        for term in wanted
    }
    ordered_terms = sorted(wanted)
    rarest = sorted(wanted, key=lambda term: (-idf.get(term, 0.0), term))[:3]
    scores: list[float] = []
    for original, tokens in zip(texts, token_lists, strict=True):
        counts = Counter(tokens)
        length = len(tokens) or 1
        normalizer = 1.2 * (1 - 0.75 + 0.75 * length / max(average_length, 1.0))
        score = 0.0
        for term in ordered_terms:
            frequency = counts.get(term, 0)
            if frequency:
                score += idf.get(term, 0.0) * frequency * 2.2 / (frequency + normalizer)
        heading = set(_TERM_PATTERN.findall(original[:_HEADING_CHARS].lower()))
        score += 0.8 * sum(idf.get(term, 0.0) for term in ordered_terms if term in heading)
        if rarest:
            covered = sum(1 for term in rarest if counts.get(term))
            score += 1.5 * covered / len(rarest) * idf.get(rarest[0], 0.0)
        scores.append(score)
    peak = max(scores) if scores else 0.0
    if hints and peak > 0:
        for index, original in enumerate(texts):
            leading = original[:_HEADING_CHARS].lower()
            if any(hint.search(leading) for hint in hints):
                scores[index] += _AFFINITY_BONUS * peak
    return scores


__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "search_pdf_pages",
]