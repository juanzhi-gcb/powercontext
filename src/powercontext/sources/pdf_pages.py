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
_HITS_PER_QUERY = 40
_MAX_CANDIDATES = 80


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
    from powercontext.artifacts import MemoryCitation as Citation
    from powercontext.builtin.runtime.models import GetMemoryEntryRequest, SearchMemoryRequest

    scored: dict[tuple[str, str, str], MemoryHit] = {}
    for subquery in _subqueries(terms):
        page = await memory.search(SearchMemoryRequest(query=subquery, mode="fts", limit=_HITS_PER_QUERY))  # type: ignore[attr-defined]
        for hit in page.hits:
            identifier = (hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id)
            scored.setdefault(identifier, hit)

    if not scored:
        return ()
    hits = tuple(scored.values())
    scores = _bm25_scores(terms, tuple(hit.text for hit in hits))
    ordered = [
        hit
        for _score, hit in sorted(
            zip(scores, hits, strict=True),
            key=lambda pair: (-pair[0], pair[1].entry_id),
        )
    ][:_MAX_CANDIDATES]
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
    terms: list[str] = []
    for term in _TERM_PATTERN.findall(question.lower()):
        if term in _STOPWORDS or len(term) < 2 or term in terms:
            continue
        terms.append(term)
    return tuple(terms)


def _subqueries(terms: tuple[str, ...]) -> tuple[str, ...]:
    """Ask several two-term questions because long FTS queries are admitted too sparsely."""

    focused = terms[:_MAX_QUERY_TERMS]
    queries = [" ".join(pair) for pair in combinations(focused, 2)]
    queries.extend(focused)
    return tuple(queries)


def _bm25_scores(terms: tuple[str, ...], texts: tuple[str, ...], /) -> list[float]:
    """Rank candidate pages with BM25 so rare question terms dominate boilerplate."""

    token_lists = [_TERM_PATTERN.findall(text.lower()) for text in texts]
    total = len(token_lists)
    if not total:
        return []
    average_length = sum(len(tokens) for tokens in token_lists) / total
    document_frequency: dict[str, int] = {}
    for tokens in token_lists:
        for term in set(tokens):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    idf = {
        term: math.log(1 + (total - document_frequency.get(term, 0) + 0.5) / (document_frequency.get(term, 0) + 0.5))
        for term in set(terms)
    }
    scores: list[float] = []
    for tokens in token_lists:
        counts = Counter(tokens)
        length = len(tokens) or 1
        normalizer = 1.2 * (1 - 0.75 + 0.75 * length / max(average_length, 1.0))
        score = 0.0
        for term in terms:
            frequency = counts.get(term, 0)
            if frequency:
                score += idf.get(term, 0.0) * frequency * 2.2 / (frequency + normalizer)
        scores.append(score)
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