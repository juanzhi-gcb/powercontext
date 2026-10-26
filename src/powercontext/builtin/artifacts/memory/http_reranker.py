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

"""HTTP cross-encoder reranking for coarse Memory search candidates."""

from __future__ import annotations

import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision, _validate_bounds
from powercontext.builtin.inference import InferenceUsage

HTTP_MEMORY_RERANK_POLICY_ID = "http-cross-encoder-v1"

_SCORE_FIELDS = frozenset({"rank", "score"})
_RESPONSE_FIELDS = frozenset({"scores"})


class HTTPMemoryReranker:
    """Score coarse candidates through one HTTP service and select globally.

    The service assigns a score to each candidate without knowing the other candidates, so batching
    is a transport concern only: every candidate keeps the rank it had in the full coarse pool and the
    final selection is made once, across all batches.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = HTTP_MEMORY_RERANK_POLICY_ID,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")  # noqa: TRY003
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size
        self.policy_id = policy_id

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score every candidate once and select the globally best coarse ranks."""

        _validate_bounds(len(candidates), limit)
        scores: dict[int, float] = {}
        requests = 0
        for batch in _batches(len(candidates), self._batch_size):
            body = {
                "query": query,
                "candidates": [{"rank": rank, "text": candidates[rank - 1].text} for rank in batch],
            }
            response = await self._client.post(self._endpoint, json=body)
            requests += 1
            response.raise_for_status()
            scores.update(_parse_scores(response, batch))
        selected = tuple(rank for rank, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit])
        return MemoryRerankDecision(selected_ranks=selected, usage=InferenceUsage(requests=requests))


def _batches(candidate_count: int, batch_size: int) -> tuple[tuple[int, ...], ...]:
    ranks = range(1, candidate_count + 1)
    return tuple(tuple(ranks[start : start + batch_size]) for start in range(0, candidate_count, batch_size))


def _parse_scores(response: httpx.Response, batch: tuple[int, ...]) -> dict[int, float]:
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise ValueError("reranker response is not valid JSON") from error  # noqa: TRY003
    if not isinstance(payload, dict) or set(payload) != _RESPONSE_FIELDS:
        raise ValueError("reranker response must contain exactly the scores field")  # noqa: TRY003
    entries = payload["scores"]
    if not isinstance(entries, list):
        raise ValueError("reranker scores must be a list")  # noqa: TRY003
    expected = set(batch)
    scores: dict[int, float] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _SCORE_FIELDS:
            raise ValueError("reranker score entries must contain exactly rank and score")  # noqa: TRY003
        rank = entry["rank"]
        if type(rank) is not int or rank not in expected:
            raise ValueError("reranker score rank must address a candidate sent in this batch")  # noqa: TRY003
        if rank in scores:
            raise ValueError("reranker score rank must appear at most once per batch")  # noqa: TRY003
        score = entry["score"]
        if isinstance(score, bool) or not isinstance(score, int | float) or not math.isfinite(score):
            raise ValueError("reranker score must be a finite number")  # noqa: TRY003
        scores[rank] = float(score)
    if set(scores) != expected:
        raise ValueError("reranker response must score every candidate in this batch")  # noqa: TRY003
    return scores


__all__ = [
    "HTTP_MEMORY_RERANK_POLICY_ID",
    "HTTPMemoryReranker",
]