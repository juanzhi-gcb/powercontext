"""Tokenisation and lightweight TF-IDF helpers.

The corpus mixes Chinese prose with Python identifiers, so the tokenizer emits
two kinds of terms:

* ASCII identifiers (whole token plus snake_case / camelCase parts);
* CJK character bigrams, which need no dictionary and still let
  ``"金额下限"`` match ``"金额下限筛选"``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

_ASCII_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CJK_RUN = re.compile(r"[一-鿿]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or of to in on for with without by from as at is are be been
    this that these those it its if then than when while not no do does did
    must should shall can may will would could return returns returned
    test tests def class import from self none true false
    """.split()
)

_CJK_STOP_BIGRAMS: frozenset[str] = frozenset(
    """必须 不得 需要 可以 我们 你们 他们 这个 那个 以及 或者 如果 时候 进行 使用
    对应 相关 指定 传入 返回 结果 调用 参数 一个 不是""".split()
)


def _split_identifier(token: str) -> list[str]:
    parts: list[str] = []
    for chunk in token.split("_"):
        if not chunk:
            continue
        parts.extend(_CAMEL_BOUNDARY.split(chunk))
    return [part.lower() for part in parts if part]


def tokenize(text: str) -> list[str]:
    """Return the weighted term list for ``text`` (duplicates preserved)."""

    if not text:
        return []
    lowered = text.lower()
    terms: list[str] = []

    for match in _ASCII_TOKEN.finditer(text):
        token = match.group(0)
        if token.startswith("__"):
            continue
        full = token.lower()
        if len(full) >= 2 and full not in STOPWORDS:
            terms.append(full)
        if "_" in token or _CAMEL_BOUNDARY.search(token):
            for part in _split_identifier(token):
                if len(part) >= 2 and part not in STOPWORDS:
                    terms.append(part)

    for match in _CJK_RUN.finditer(lowered):
        run = match.group(0)
        if len(run) <= 4:
            terms.append(run)
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in _CJK_STOP_BIGRAMS:
                terms.append(bigram)

    return terms


def term_counts(text: str, *, boost: float = 1.0) -> Counter[str]:
    """Return ``Counter`` of terms with ``boost`` applied to the raw count."""

    counts: Counter[str] = Counter()
    for term in tokenize(text):
        counts[term] += boost
    return counts


def idf(document_frequency: int, total_documents: int) -> float:
    return math.log(1.0 + total_documents / (1.0 + document_frequency))


def tf_weight(raw_count: float) -> float:
    return 1.0 + math.log(raw_count) if raw_count > 0 else 0.0


def dedupe(terms: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for term in terms:
        seen.setdefault(term, None)
    return list(seen)
