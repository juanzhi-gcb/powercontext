from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol
from urllib.request import Request, urlopen


class EvidenceValidationError(ValueError):
    pass


class Comparator(Protocol):
    version: str

    def compare(
        self, candidate: dict[str, Any], historical: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


def tokens(text: str) -> set[str]:
    stop = {"the", "and", "with", "from", "that", "this", "using", "into", "than"}
    return {
        token
        for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        if len(token) > 1 and token not in stop
    }


class DeterministicComparator:
    version = "deterministic-mechanism-v1"

    def compare(
        self, candidate: dict[str, Any], historical: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        candidate_tokens = tokens(candidate["mechanism"])
        historical_tokens = tokens(historical["mechanism"])
        union = candidate_tokens | historical_tokens
        similarity = len(candidate_tokens & historical_tokens) / len(union) if union else 0.0
        differentiator = candidate.get("differentiator", "").strip()
        difference = (
            differentiator
            if differentiator
            else "No changed causal condition was declared; the mechanisms must be treated as potentially equivalent."
        )
        return {
            "similarity": round(similarity, 6),
            "difference": difference,
            "evidence_ids": [item["id"] for item in evidence],
        }


class OpenAIComparator:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.version = f"{model}-mechanism-json-v1"

    def compare(
        self, candidate: dict[str, Any], historical: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        allowed_ids = {item["id"] for item in evidence}
        prompt = {
            "candidate_mechanism": candidate["mechanism"],
            "candidate_differentiator": candidate.get("differentiator", ""),
            "historical_mechanism": historical["mechanism"],
            "evidence": [
                {"id": item["id"], "locator": item["locator"], "excerpt": item["excerpt"]}
                for item in evidence
            ],
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Compare causal mechanisms, not surface topic similarity. Return JSON with "
                            "similarity (0..1), difference (string), and evidence_ids (array). "
                            "Use only supplied evidence IDs; never invent a citation.",
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            payload = json.load(response)
        result = json.loads(payload["choices"][0]["message"]["content"])
        similarity = float(result["similarity"])
        if not 0 <= similarity <= 1:
            raise EvidenceValidationError("Comparator similarity must be between 0 and 1")
        evidence_ids = result.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or not set(evidence_ids) <= allowed_ids:
            raise EvidenceValidationError("Comparator returned an unknown evidence ID")
        return {
            "similarity": similarity,
            "difference": str(result["difference"]),
            "evidence_ids": evidence_ids,
        }


def build_comparator() -> Comparator:
    model = os.getenv("LLM_MODEL", "")
    if model:
        return OpenAIComparator(
            os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("LLM_API_KEY", ""),
            model,
        )
    return DeterministicComparator()
