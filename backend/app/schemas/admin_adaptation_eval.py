from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AdaptationEvalRunStatus = Literal["queued", "running", "success", "error"]
AdaptationEvalCaseResultStatus = Literal["passed", "failed", "error"]
AdaptationEvalVerdict = Literal["approved", "needs_rework"]
AdaptationEvalScenarioType = Literal[
    "positive",
    "negative_control",
    "partial_match",
    "noise",
    "regression",
]
AdaptationEvalExportArtifact = Literal["case_results", "metrics"]


class AdaptationEvalHistoricalTaskPayload(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    chat_messages: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AdaptationEvalProbeTaskPayload(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    custom_rules: list[dict[str, Any]] = Field(default_factory=list)
    related_tasks: list[dict[str, Any]] = Field(default_factory=list)
    attachment_names: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AdaptationEvalExpectedIssue(BaseModel):
    code: str | None = Field(default=None, max_length=255)
    severity: Literal["low", "medium", "high"] | None = None
    message: str = ""
    source: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="allow")


class AdaptationEvalCasePayload(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    scenario_type: AdaptationEvalScenarioType = "positive"
    historical_tasks: list[AdaptationEvalHistoricalTaskPayload] = Field(default_factory=list)
    probe_task: AdaptationEvalProbeTaskPayload
    expected_captured_questions: list[str] = Field(default_factory=list)
    expected_retrieved_questions: list[str] = Field(default_factory=list)
    expected_context_questions: list[str] = Field(default_factory=list)
    expected_verdict: AdaptationEvalVerdict = "needs_rework"
    expected_context_issues: list[AdaptationEvalExpectedIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AdaptationEvalImportPayload(BaseModel):
    dataset_name: str = Field(min_length=3, max_length=255)
    project_id: str
    cases: list[AdaptationEvalCasePayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_unique_cases(self) -> AdaptationEvalImportPayload:
        external_ids = [case.external_id for case in self.cases]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("Case external_id values must be unique.")
        return self


class AdaptationEvalQualityGates(BaseModel):
    capture_recall_min: float = Field(default=0.95, ge=0, le=1)
    retrieval_recall_at_k_min: float = Field(default=0.8, ge=0, le=1)
    context_question_f1_min: float = Field(default=0.75, ge=0, le=1)
    context_issue_f1_min: float = Field(default=0.7, ge=0, le=1)
    duplicate_rate_max: float = Field(default=0.1, ge=0, le=1)
    require_full_improvement: bool = False

    model_config = ConfigDict(extra="forbid")


class AdaptationEvalRunConfig(BaseModel):
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    cleanup_synthetic_tasks: bool = True
    quality_gates: AdaptationEvalQualityGates = Field(
        default_factory=AdaptationEvalQualityGates
    )

    model_config = ConfigDict(extra="forbid")


class AdaptationEvalDatasetRead(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    name: str
    cases_total: int
    last_run_id: str | None = None
    last_run_status: AdaptationEvalRunStatus | None = None
    created_at: datetime
    updated_at: datetime


class AdaptationEvalCaseRead(BaseModel):
    id: str
    external_id: str
    scenario_type: str
    historical_tasks: list[dict[str, Any]]
    probe_task: dict[str, Any]
    expected_captured_questions: list[str]
    expected_retrieved_questions: list[str]
    expected_context_questions: list[str]
    expected_verdict: AdaptationEvalVerdict
    expected_context_issues: list[dict[str, Any]]
    metadata: dict[str, Any]
    updated_at: datetime


class AdaptationEvalDatasetDetailRead(AdaptationEvalDatasetRead):
    cases: list[AdaptationEvalCaseRead]


class AdaptationEvalImportResultRead(BaseModel):
    dataset: AdaptationEvalDatasetDetailRead
    imported_cases: int
    warnings: list[str] = Field(default_factory=list)


class AdaptationEvalRunCreateRead(BaseModel):
    id: str
    dataset_id: str
    status: AdaptationEvalRunStatus
    config: AdaptationEvalRunConfig
    created_at: datetime


class AdaptationEvalRunListItemRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: AdaptationEvalRunStatus
    config: AdaptationEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class AdaptationEvalRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[AdaptationEvalRunListItemRead]


class AdaptationEvalCaseResultRead(BaseModel):
    id: str
    case_id: str
    case_external_id: str
    scenario_type: str
    status: AdaptationEvalCaseResultStatus
    core_graph_run_id: str | None
    full_graph_run_id: str | None
    synthetic_task_ids: list[str]
    expected_result: dict[str, Any]
    actual_result: dict[str, Any]
    diffs: dict[str, Any]
    metrics: dict[str, Any]
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class AdaptationEvalRunRead(AdaptationEvalRunListItemRead):
    case_results: list[AdaptationEvalCaseResultRead] = Field(default_factory=list)
