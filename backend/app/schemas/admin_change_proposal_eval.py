from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChangeProposalEvalMode = Literal["route_then_extract", "extract_all"]
ChangeProposalEvalExpectedAction = Literal["create", "skip_duplicate", "ignore"]
ChangeProposalEvalCaseStatus = Literal["passed", "failed", "error"]
ChangeProposalEvalRunStatus = Literal["success", "partial_error", "error"]


class ChangeProposalEvalCasePayload(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    project_id: str | None = None
    task_id: str | None = None
    task_title: str = Field(min_length=1, max_length=500)
    task_status: str = Field(default="draft", max_length=64)
    task_content: str = ""
    message_content: str = Field(min_length=1, max_length=4000)
    requested_agent: str | None = Field(default=None, max_length=100)
    expected_is_proposal: bool
    expected_proposal_text: str | None = None
    expected_duplicate: bool = False
    expected_duplicate_of: str | None = Field(default=None, max_length=255)
    expected_action: ChangeProposalEvalExpectedAction
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_expected_payload(self) -> Self:
        if self.expected_is_proposal and not (self.expected_proposal_text or "").strip():
            raise ValueError("expected_proposal_text is required for proposal cases.")
        if not self.expected_is_proposal and self.expected_action != "ignore":
            raise ValueError("Non-proposal cases must use expected_action='ignore'.")
        if self.expected_duplicate and self.expected_action != "skip_duplicate":
            raise ValueError("Duplicate cases must use expected_action='skip_duplicate'.")
        return self


class ChangeProposalEvalRunConfig(BaseModel):
    mode: ChangeProposalEvalMode = "route_then_extract"
    semantic_match_threshold: float = Field(default=0.55, ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class ChangeProposalEvalRunPayload(BaseModel):
    project_id: str | None = None
    config: ChangeProposalEvalRunConfig = Field(default_factory=ChangeProposalEvalRunConfig)
    cases: list[ChangeProposalEvalCasePayload] = Field(default_factory=list, min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_unique_cases(self) -> Self:
        external_ids = [case.external_id for case in self.cases]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("Case external_id values must be unique.")
        return self


class ChangeProposalEvalCaseResultRead(BaseModel):
    case_external_id: str
    status: ChangeProposalEvalCaseStatus
    expected: dict[str, Any]
    actual: dict[str, Any]
    metrics: dict[str, Any]
    route_graph_run_id: str | None = None
    change_graph_run_id: str | None = None
    latency_ms: int | None = None
    error_message: str | None = None


class ChangeProposalEvalRunRead(BaseModel):
    status: ChangeProposalEvalRunStatus
    config: ChangeProposalEvalRunConfig
    summary_metrics: dict[str, Any]
    case_results: list[ChangeProposalEvalCaseResultRead]
    started_at: datetime
    finished_at: datetime
    latency_ms: int
