from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from .comparator import Comparator, EvidenceValidationError
from .models import MachineDecision

RULES_VERSION = "research-ci-rules-v1"


def check(
    name: str, status: str, reason: str, detail: str, refs: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "reason_code": reason,
        "detail": detail,
        "evidence_ids": refs or [],
    }


def constraints_from_context(entries: list[dict[str, Any]]) -> dict[str, Any]:
    constraints: dict[str, Any] = {
        "min_gpu_count": 2,
        "max_pilot_hours": 48,
        "min_storage_gb": 50,
        "problem_before_baseline": True,
    }
    for entry in entries:
        if entry.get("kind") != "research_constitution":
            continue
        try:
            value = json.loads(entry.get("text", ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            for key in constraints:
                if key in value and isinstance(value[key], (int, float, bool)):
                    constraints[key] = value[key]
    return constraints


def _quote(text: str, limit: int = 80) -> str:
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    cut = value[:limit]
    punctuation = max(
        cut.rfind("；"),
        cut.rfind(";"),
        cut.rfind("。"),
        cut.rfind("."),
        cut.rfind("，"),
        cut.rfind(","),
    )
    boundary = punctuation if punctuation >= limit / 2 else max(punctuation, cut.rfind(" "))
    return (cut[:boundary] if boundary >= limit / 2 else cut).rstrip() + "…"


def _trim_sentence(text: str) -> str:
    return text.strip().rstrip("。；;. \t\n")


def minimal_experiment(
    attempt: dict[str, Any], comparison: dict[str, Any] | None = None
) -> dict[str, str]:
    differentiator = _quote(_trim_sentence(attempt.get("differentiator") or ""))
    competing = [
        item.strip()
        for item in attempt.get("competing_explanations") or []
        if isinstance(item, str) and item.strip()
    ]
    failure = _trim_sentence(attempt.get("failure_condition") or "")
    task = attempt.get("task") or "general"
    target = f"{task} 的任务分数" if task != "general" else "目标任务分数"
    historical = (
        _quote(comparison["title"], 48)
        if comparison
        and comparison.get("evidence")
        and float(comparison.get("mechanism_similarity") or 0) >= 0.12
        else ""
    )
    control_name = _quote(competing[0], 48) if competing else historical
    hours = attempt.get("pilot_hours", 0)
    gpus = attempt.get("gpu_count", 0)

    hypothesis = (
        (
            f"如果「{differentiator}」成立，那么在「{historical}」的任务设置下复现时，结果应出现可测差异；"
            "若没有差异，就不能主张这条路线比它多提供了机制信息。"
            if historical
            else f"如果「{differentiator}」成立，最小实验应在「条件未改变」和「条件已改变」两组之间产生可测差异。"
        )
        if differentiator
        else (
            f"尚未声明差异：先写清与「{historical}」相比改变了哪个因果条件；没有这句话，假设不可检验。"
            if historical
            else "尚未声明差异：先写清改变了哪个因果条件；没有这句话，假设不可检验。"
        )
    )
    intervention = (
        (
            f"只改「{differentiator}」；数据、模型版本、预算和评测保持固定，并以「{historical}」为参照。"
            if historical
            else f"只改「{differentiator}」；其余条件全部固定。"
        )
        if differentiator
        else "待补：写出唯一改变的变量；没有它就没有可执行的干预。"
    )
    control = (
        f"用「{_quote(competing[0], 48)}」在相同数据和预算下跑同一套评测；如果它也能解释结果，新机制不成立。"
        if competing
        else (
            f"先复现「{historical}」的做法作为控制；它是当前最接近、且有可定位证据的历史记录。"
            if historical
            else "待补：写下至少一个能解释同一结果的简单替代方案。"
        )
    )
    metric = (
        f"机制指标：同一测量流程在「条件未改变」和「条件已改变」两组上的读数差，直接对应「{differentiator}」；"
        f"任务指标：{target}。开跑前写死两者的计算方式。"
        if differentiator
        else "待补：先确定用什么数值判断新条件成立；没有可测指标就无法预注册。"
    )
    threshold = (
        f"在 {hours}h、{gpus} 块 GPU 内，让「{control_name}」也跑同一套评测；"
        "机制指标的差值必须大于它重复运行的波动（默认重复 2 次，开跑前可改）。"
        if control_name
        else "待补：先确定控制组，才能设通过阈值。"
    )
    stop_condition = f"{failure or '机制指标没有分离'}；首轮超过 {hours}h 也停止。"

    return {
        "hypothesis": hypothesis,
        "intervention": intervention,
        "control": control,
        "metric": metric,
        "threshold": threshold,
        "stop_condition": stop_condition,
    }


def evaluate(
    attempt: dict[str, Any],
    cutoff: datetime,
    candidates: list[dict[str, Any]],
    evidence_by_attempt: dict[str, list[dict[str, Any]]],
    comparator: Comparator,
    comparator_version: str,
    embedding_version: str,
    context_entries: list[dict[str, Any]],
    context_refs: list[dict[str, Any]],
    context_warning: str | None = None,
) -> dict[str, Any]:
    comparisons = []
    invalid_comparison = False
    for historical in candidates:
        evidence = evidence_by_attempt.get(historical["id"], [])
        try:
            comparison = comparator.compare(attempt, historical, evidence)
            difference = comparison["difference"]
            similarity = comparison["similarity"]
            cited_ids = comparison["evidence_ids"]
            if not 0 <= similarity <= 1:
                raise EvidenceValidationError("Comparator similarity must be between 0 and 1")
            if not isinstance(cited_ids, list) or not set(cited_ids) <= {
                item["id"] for item in evidence
            }:
                raise EvidenceValidationError("Comparator returned an unknown evidence ID")
        except (EvidenceValidationError, ValueError, KeyError, TypeError) as error:
            invalid_comparison = True
            difference = f"Comparison rejected: {error}"
            similarity = 0.0
            cited_ids = []
        comparisons.append(
            {
                "attempt_id": historical["id"],
                "title": historical["title"],
                "task": historical["task"],
                "domain": historical["domain"],
                "historical_decision": historical.get("historical_decision"),
                "available_at": historical["available_at"],
                "vector_distance": historical.get("vector_distance"),
                "fts_score": historical.get("fts_score"),
                "vector_rank": historical.get("vector_rank"),
                "fts_rank": historical.get("fts_rank"),
                "fused_score": historical["fused_score"],
                "mechanism_similarity": similarity,
                "mechanism_difference": difference,
                "evidence_ids": cited_ids,
                "evidence": [item for item in evidence if item["id"] in cited_ids],
            }
        )

    constraints = constraints_from_context(context_entries)
    attempt_ref = f"attempt:{attempt['id']}#resources"
    baseline_gate_failed = constraints["problem_before_baseline"] and attempt["baseline_first"]
    checks = [
        check(
            "engineering.data",
            "pass" if attempt["data_ready"] else "fail",
            "DATA_READY" if attempt["data_ready"] else "DATA_NOT_READY",
            "Minimum usable data must be available before mechanism work continues.",
            [attempt_ref],
        ),
        check(
            "engineering.checkpoint",
            "pass" if attempt["checkpoint_ready"] else "fail",
            "CHECKPOINT_READY" if attempt["checkpoint_ready"] else "CHECKPOINT_MISSING",
            "The required model checkpoint must be available at the pinned revision.",
            [attempt_ref],
        ),
        check(
            "engineering.gpu",
            "pass" if attempt["gpu_count"] >= constraints["min_gpu_count"] else "fail",
            "GPU_BUDGET_OK"
            if attempt["gpu_count"] >= constraints["min_gpu_count"]
            else "GPU_BUDGET_INSUFFICIENT",
            f"Available GPUs: {attempt['gpu_count']}; required: {constraints['min_gpu_count']}.",
            [attempt_ref],
        ),
        check(
            "engineering.closed_loop",
            "pass" if attempt["pilot_hours"] <= constraints["max_pilot_hours"] else "fail",
            "PILOT_WITHIN_BUDGET"
            if attempt["pilot_hours"] <= constraints["max_pilot_hours"]
            else "PILOT_EXCEEDS_BUDGET",
            f"Pilot: {attempt['pilot_hours']}h; maximum: {constraints['max_pilot_hours']}h.",
            [attempt_ref],
        ),
        check(
            "engineering.storage",
            "pass" if attempt["storage_gb"] >= constraints["min_storage_gb"] else "fail",
            "STORAGE_BUDGET_OK"
            if attempt["storage_gb"] >= constraints["min_storage_gb"]
            else "STORAGE_BUDGET_INSUFFICIENT",
            f"Available storage: {attempt['storage_gb']}GB; required: {constraints['min_storage_gb']}GB.",
            [attempt_ref],
        ),
        check(
            "process.problem_first",
            "fail" if baseline_gate_failed else "pass",
            "BASELINE_BEFORE_PROBLEM" if baseline_gate_failed else "PROBLEM_BEFORE_BASELINE",
            "A baseline must not be selected first and then reverse-packaged as a research question.",
            [attempt_ref],
        ),
    ]

    coverage_missing = [item["attempt_id"] for item in comparisons[:3] if not item["evidence"]]
    checks.append(
        check(
            "evidence.coverage",
            "warn" if not comparisons or coverage_missing else "pass",
            "EVIDENCE_MISSING" if not comparisons or coverage_missing else "EVIDENCE_LOCATABLE",
            "Every key historical comparison needs at least one source locator available at the cutoff.",
            [item["id"] for comparison in comparisons[:3] for item in comparison["evidence"]],
        )
    )
    checks.append(
        check(
            "evidence.discrimination",
            "pass" if attempt.get("competing_explanations") else "warn",
            "COMPETING_EXPLANATION_DECLARED"
            if attempt.get("competing_explanations")
            else "COMPETING_EXPLANATION_MISSING",
            "The minimum experiment must distinguish the proposed mechanism from a trivial alternative.",
        )
    )

    top = comparisons[0] if comparisons else None
    repackaged = bool(
        top
        and top["mechanism_similarity"] >= 0.55
        and not attempt.get("differentiator", "").strip()
    )
    checks.append(
        check(
            "mechanism.repaint",
            "fail" if repackaged else ("unknown" if top is None else "pass"),
            "MECHANISM_REPACKAGED" if repackaged else "CHANGED_CONDITION_DECLARED",
            top["mechanism_difference"]
            if top
            else "No eligible historical mechanism was recalled.",
            top["evidence_ids"] if top else [],
        )
    )

    engineering_failed = any(
        item["status"] == "fail" for item in checks if item["name"].startswith("engineering.")
    )
    evidence_ids = list(
        dict.fromkeys(
            item["id"] for comparison in comparisons[:3] for item in comparison["evidence"]
        )
    )
    if invalid_comparison:
        decision = MachineDecision.INSUFFICIENT_EVIDENCE
        reason_code = "COMPARISON_OUTPUT_INVALID"
        summary = "A mechanism comparison failed citation validation, so no substantive verdict was accepted."
    elif engineering_failed or baseline_gate_failed:
        decision = MachineDecision.NO_GO
        reason_code = "DETERMINISTIC_GATE_FAILED"
        summary = "A deterministic resource, closed-loop, or problem-first gate failed."
    elif repackaged:
        decision = MachineDecision.NO_GO
        reason_code = "MECHANISM_REPACKAGED"
        summary = (
            "The closest mechanism is highly similar and no changed causal condition was declared."
        )
    elif not comparisons or not top["evidence"]:
        decision = MachineDecision.INSUFFICIENT_EVIDENCE
        reason_code = "NO_LOCATABLE_HISTORICAL_EVIDENCE"
        summary = (
            "The system found insufficient cutoff-valid evidence for a substantiated decision."
        )
    elif top["mechanism_similarity"] >= 0.12 or top["fused_score"] > 0.01:
        decision = MachineDecision.CONDITIONAL_GO
        reason_code = "DIFFERENTIATED_MECHANISM"
        summary = "A changed condition is declared; proceed only through the minimum discriminating experiment."
    else:
        decision = MachineDecision.INSUFFICIENT_EVIDENCE
        reason_code = "MECHANISM_RELATION_UNCERTAIN"
        summary = "Retrieval did not establish a reliable mechanism relation; add a more specific mechanism description or a closer comparison."

    if context_warning:
        checks.append(check("context.restore", "warn", "CONTEXT_UNAVAILABLE", context_warning))

    return {
        "id": str(uuid.uuid4()),
        "attempt_id": attempt["id"],
        "attempt": {
            "title": attempt["title"],
            "idea": attempt["idea"],
            "mechanism": attempt["mechanism"],
            "differentiator": attempt.get("differentiator", ""),
        },
        "cutoff": cutoff.isoformat(),
        "machine_decision": decision.value,
        "reason_code": reason_code,
        "summary": summary,
        "evidence_ids": evidence_ids,
        "comparisons": comparisons,
        "checks": checks,
        "constraints": constraints,
        "minimal_experiment": minimal_experiment(attempt, comparisons[0] if comparisons else None),
        "context_refs": context_refs,
        "versions": {
            "model": comparator_version,
            "embedding": embedding_version,
            "rules": RULES_VERSION,
            "retrieval": "seekdb-vector-fts-rrf-v1",
        },
    }
