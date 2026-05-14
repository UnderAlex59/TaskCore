from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrchestratorEvalImportFormat = Literal["json", "csv"]
OrchestratorEvalRunStatus = Literal["queued", "running", "success", "error"]
OrchestratorEvalCaseStatus = Literal["passed", "failed", "error"]
OrchestratorRoutingMode = Literal["auto", "forced"]
OrchestratorMessageType = Literal["general", "question", "change_proposal"]


class OrchestratorEvalExpectedRoute(BaseModel):
    ai_response_required: bool | None = None
    target_agent_key: str | None = None
    message_type: OrchestratorMessageType | None = None
    routing_mode: OrchestratorRoutingMode | None = None
    reason_contains: str | None = None

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalInput(BaseModel):
    project_id: str
    task_id: str | None = None
    task_title: str = Field(min_length=1, max_length=500)
    task_status: str = Field(default="draft", max_length=64)
    task_content: str = ""
    validation_result: dict[str, Any] | None = None
    message_content: str = Field(min_length=1, max_length=4000)
    requested_agent: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalCaseImport(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    input: OrchestratorEvalInput
    expected_route: OrchestratorEvalExpectedRoute = Field(
        default_factory=OrchestratorEvalExpectedRoute
    )

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalStructuredImport(BaseModel):
    dataset_name: str = Field(min_length=3, max_length=255)
    project_id: str
    cases: list[OrchestratorEvalCaseImport] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalImportPayload(BaseModel):
    format: OrchestratorEvalImportFormat = "json"
    dataset_name: str | None = Field(default=None, min_length=3, max_length=255)
    project_id: str | None = None
    payload: OrchestratorEvalStructuredImport | None = None
    content: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def validate_utf8_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value.encode("utf-8")
        return value


class OrchestratorEvalRunConfig(BaseModel):
    compare_reason: bool = True

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalPlaygroundRunPayload(BaseModel):
    input: OrchestratorEvalInput
    expected_route: OrchestratorEvalExpectedRoute | None = None
    config: OrchestratorEvalRunConfig = Field(default_factory=OrchestratorEvalRunConfig)

    model_config = ConfigDict(extra="forbid")


class OrchestratorEvalCaseRead(BaseModel):
    id: str
    external_id: str
    input: OrchestratorEvalInput
    expected_route: dict[str, Any]
    updated_at: datetime


class OrchestratorEvalDatasetRead(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    name: str
    cases_total: int
    last_run_id: str | None = None
    last_run_status: OrchestratorEvalRunStatus | None = None
    created_at: datetime
    updated_at: datetime


class OrchestratorEvalDatasetDetailRead(OrchestratorEvalDatasetRead):
    cases: list[OrchestratorEvalCaseRead]


class OrchestratorEvalImportResultRead(BaseModel):
    dataset: OrchestratorEvalDatasetDetailRead
    imported_cases: int
    warnings: list[str] = Field(default_factory=list)


class OrchestratorEvalPlaygroundResultRead(BaseModel):
    status: OrchestratorEvalCaseStatus
    input: OrchestratorEvalInput
    expected_route: dict[str, Any]
    actual_route: dict[str, Any]
    metrics: dict[str, Any]
    graph_run_id: str | None
    latency_ms: int | None
    error_message: str | None = None


class OrchestratorEvalCaseResultRead(BaseModel):
    id: str
    case_id: str
    case_external_id: str
    input: OrchestratorEvalInput
    expected_route: dict[str, Any]
    actual_route: dict[str, Any]
    status: OrchestratorEvalCaseStatus
    metrics: dict[str, Any]
    graph_run_id: str | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class OrchestratorEvalRunCreateRead(BaseModel):
    id: str
    dataset_id: str
    status: OrchestratorEvalRunStatus
    config: OrchestratorEvalRunConfig
    created_at: datetime


class OrchestratorEvalRunListItemRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: OrchestratorEvalRunStatus
    config: OrchestratorEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class OrchestratorEvalRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[OrchestratorEvalRunListItemRead]


class OrchestratorEvalRunRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: OrchestratorEvalRunStatus
    config: OrchestratorEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    case_results: list[OrchestratorEvalCaseResultRead] = Field(default_factory=list)
