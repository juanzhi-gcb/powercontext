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

"""Coalesce concurrent Embedding requests and cache successful vectors."""

from __future__ import annotations

import asyncio
import itertools
from collections import OrderedDict
from collections.abc import Sequence

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage

DEFAULT_MAX_BATCH_SIZE = 64
DEFAULT_COALESCE_MS = 5.0
DEFAULT_CACHE_SIZE = 1024

_VECTOR_FUTURE = asyncio.Future[EmbeddingVector]


class CoalescingEmbeddingModel:
    """Share in-flight Embedding work and retain successful vectors.

    Callers keep their own ordering and duplicate positions, while the provider only sees the
    distinct texts that are still missing, at most ``max_batch_size`` per request.
    """

    def __init__(
        self,
        model: object,
        *,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        coalesce_ms: float = DEFAULT_COALESCE_MS,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        _require_positive_int("max_batch_size", max_batch_size)
        _require_non_negative_int("cache_size", cache_size)
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, int | float):
            raise ValueError("coalesce_ms must be a number")  # noqa: TRY003
        if coalesce_ms < 0:
            raise ValueError("coalesce_ms must not be negative")  # noqa: TRY003
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._pending: OrderedDict[str, _VECTOR_FUTURE] = OrderedDict()
        self._inflight: dict[str, tuple[_VECTOR_FUTURE, int]] = {}
        self._text_batch: dict[str, int] = {}
        self._batch_usage: dict[int, InferenceUsage] = {}
        self._batch_ids = itertools.count(1)
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def profile(self) -> object:
        return getattr(self._model, "profile")

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        """Return vectors in the caller's original order and duplicate positions."""

        requested = tuple(texts)
        if not requested:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        unique = tuple(dict.fromkeys(requested))
        futures: dict[str, _VECTOR_FUTURE] = {}
        cached: set[str] = set()
        for text in unique:
            future, from_cache = self._claim(text)
            futures[text] = future
            if from_cache:
                cached.add(text)

        if self._pending:
            await asyncio.sleep(self._coalesce_seconds)
            self._dispatch_pending()

        vectors: list[EmbeddingVector] = []
        for text in requested:
            vectors.append(await asyncio.shield(futures[text]))
        return EmbeddingResult(vectors=tuple(vectors), usage=self._usage_for(unique, cached))

    def _claim(self, text: str) -> tuple[_VECTOR_FUTURE, bool]:
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)
            future: _VECTOR_FUTURE = asyncio.get_running_loop().create_future()
            future.set_result(cached)
            return future, True
        known = self._inflight.get(text)
        if known is not None:
            return known[0], False
        waiting = self._pending.get(text)
        if waiting is not None:
            return waiting, False
        future = asyncio.get_running_loop().create_future()
        self._pending[text] = future
        return future, False

    def _dispatch_pending(self) -> None:
        if not self._pending:
            return
        pending = list(self._pending.items())
        self._pending.clear()
        for start in range(0, len(pending), self._max_batch_size):
            batch = pending[start : start + self._max_batch_size]
            batch_id = next(self._batch_ids)
            texts = tuple(text for text, _ in batch)
            futures = tuple(future for _, future in batch)
            for text, future in batch:
                self._inflight[text] = (future, batch_id)
                self._text_batch[text] = batch_id
            task = asyncio.get_running_loop().create_task(self._run_batch(batch_id, texts))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_batch(self, batch_id: int, texts: tuple[str, ...]) -> None:
        try:
            result = await self._model.embed(texts)  # type: ignore[attr-defined]
            vectors = tuple(result.vectors)
            if len(vectors) != len(texts):
                raise ValueError(  # noqa: TRY003
                    f"embedding provider returned {len(vectors)} vectors for {len(texts)} texts"
                )
            for text, vector in zip(texts, vectors, strict=True):
                self._store(text, vector)
                entry = self._inflight.get(text)
                if entry is not None and not entry[0].done():
                    entry[0].set_result(vector)
            self._batch_usage[batch_id] = result.usage
        except Exception as error:
            for text in texts:
                entry = self._inflight.get(text)
                if entry is not None and not entry[0].done():
                    entry[0].set_exception(error)
        finally:
            for text in texts:
                self._inflight.pop(text, None)

    def _store(self, text: str, vector: EmbeddingVector) -> None:
        if self._cache_size == 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _usage_for(self, unique: tuple[str, ...], cached: set[str]) -> InferenceUsage:
        batch_ids = {
            self._text_batch[text] for text in unique if text not in cached and text in self._text_batch
        }
        usages = [self._batch_usage[batch_id] for batch_id in batch_ids if batch_id in self._batch_usage]
        if not usages:
            return InferenceUsage(requests=0)
        return InferenceUsage(
            requests=sum(usage.requests for usage in usages),
            input_tokens=_sum_tokens([usage.input_tokens for usage in usages]),
            output_tokens=_sum_tokens([usage.output_tokens for usage in usages]),
        )


def _sum_tokens(values: list[int | None]) -> int | None:
    observed = [value for value in values if value is not None]
    return sum(observed) if observed else None


def _require_positive_int(field: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")  # noqa: TRY003


def _require_non_negative_int(field: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")  # noqa: TRY003


__all__ = ["CoalescingEmbeddingModel"]