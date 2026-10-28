from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MachineDecision(str, Enum):
    NO_GO = "NO_GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class FinalDecision(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AttemptCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    idea: str = Field(min_length=10, max_length=12000)
    mechanism: str = Field(min_length=10, max_length=12000)
    task: str = Field(default="general", max_length=100)
    domain: str = Field(default="research", max_length=100)
    failure_condition: str = Field(min_length=3, max_length=4000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    competing_explanations: list[str] = Field(default_factory=list, max_length=20)
    differentiator: str = Field(default="", max_length=4000)
    available_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    gpu_count: int = Field(default=2, ge=0, le=1024)
    data_ready: bool = True
    checkpoint_ready: bool = True
    pilot_hours: float = Field(default=24, gt=0, le=10000)
    storage_gb: float = Field(default=100, ge=0)
    baseline_first: bool = False

    @field_validator("available_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("available_at must include a timezone")
        return value


class EvidenceInput(BaseModel):
    id: str = Field(min_length=3, max_length=100)
    source_type: Literal["paper", "experiment", "log", "code_audit", "decision_record"]
    title: str = Field(min_length=2, max_length=300)
    locator: str = Field(min_length=1, max_length=2000)
    excerpt: str = Field(min_length=5, max_length=12000)
    stance: Literal["supports", "refutes", "limits"]
    published_at: datetime

    @field_validator("published_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("published_at must include a timezone")
        return value


class ResearchSourceInput(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=10, max_length=50000)
    locator: str = Field(min_length=1, max_length=1900)
    published_at: datetime
    source_type: Literal["paper", "log", "code_audit"] = "paper"
    task: str = Field(default="research", max_length=100)
    domain: str = Field(default="research", max_length=100)

    @field_validator("published_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("published_at must include a timezone")
        return value


class ResearchSourceImport(BaseModel):
    sources: list[ResearchSourceInput] = Field(min_length=1, max_length=10)


class ArchiveCard(BaseModel):
    attempt: AttemptCreate
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=100)
    historical_decision: FinalDecision | None = None


class ArchiveImport(BaseModel):
    cards: list[ArchiveCard] = Field(min_length=1, max_length=100)


class HistorySearchCreate(BaseModel):
    query: str = Field(min_length=10, max_length=12000)


class SecretaryReviewCreate(BaseModel):
    proposal_id: str = Field(min_length=3, max_length=100)
    status: Literal["accepted", "rejected", "snoozed"]
    note: str = Field(default="", max_length=2000)


class EvaluationRunCreate(BaseModel):
    attempt_id: str
    cutoff: datetime = Field(default_factory=lambda: datetime.now(UTC))
    use_context: bool = True

    @field_validator("cutoff")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("cutoff must include a timezone")
        return value


class DecisionCreate(BaseModel):
    run_id: str
    decision: FinalDecision
    reason: str = Field(min_length=5, max_length=8000)
    restart_conditions: str = Field(default="", max_length=4000)
    reviewer_alias: str = Field(default="anonymous-reviewer", max_length=100)


class ExperimentCreate(BaseModel):
    attempt_id: str
    hypothesis: str = Field(min_length=5, max_length=4000)
    intervention: str = Field(min_length=3, max_length=4000)
    control: str = Field(min_length=3, max_length=4000)
    metric: str = Field(min_length=2, max_length=500)
    threshold: str = Field(min_length=1, max_length=500)
    observed_result: str = Field(min_length=1, max_length=4000)
    outcome: Literal["supports", "refutes", "inconclusive"]
    stop_triggered: bool = False
    ran_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("ran_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("ran_at must include a timezone")
        return value


class ReplayCreate(BaseModel):
    source_run_id: str
    expected_decision: MachineDecision
    required_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_evidence_ids: list[str] = Field(default_factory=list)
