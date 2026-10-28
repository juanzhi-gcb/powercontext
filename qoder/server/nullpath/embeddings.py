from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Protocol
from urllib.request import Request, urlopen


class Embedder(Protocol):
    version: str

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    version = "hashing-char-word-64-v1"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
        features = set(words)
        features.update(
            normalized[index : index + 3] for index in range(max(0, len(normalized) - 2))
        )
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 8) for value in vector]


class OpenAIEmbedder:
    def __init__(self, base_url: str, api_key: str, model: str, dimensions: int = 64) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.version = f"{model}-{dimensions}-v1"

    def embed(self, text: str) -> list[float]:
        request = Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(
                {"model": self.model, "input": text, "dimensions": self.dimensions}
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        vector = payload["data"][0]["embedding"]
        if len(vector) != self.dimensions:
            raise ValueError(
                f"Embedding service returned {len(vector)} dimensions, expected {self.dimensions}"
            )
        return vector


def build_embedder() -> Embedder:
    model = os.getenv("EMBEDDING_MODEL", "")
    if model:
        return OpenAIEmbedder(
            os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("EMBEDDING_API_KEY", ""),
            model,
            int(os.getenv("EMBEDDING_DIMENSIONS", "64")),
        )
    return HashingEmbedder(int(os.getenv("EMBEDDING_DIMENSIONS", "64")))
