from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ValidationEvalImportFormat = Literal["json", "csv"]
ValidationEvalRunStatus = Literal["queued", "running", "success", "error"]
ValidationEvalCaseResultStatus = Literal["passed", "failed", "error"]
ValidationEvalVerdict = Literal["approved", "needs_rework"]
ValidationEvalSeverity = Literal["low", "medium", "high"]
ValidationEvalExportArtifact = Literal[
    "case_results",
    "metrics",
    "confusion_matrix",
    "ablation",
    "errors",
]


class ValidationEvalExpectedIssue(BaseModel):
    code: str | None = Field(default=None, max_length=255)
    severity: ValidationEvalSeverity | None = None
    message: str = ""
    rule_title: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="allow")


class ValidationEvalCustomRule(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    applies_to_tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ValidationEvalCaseBase(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    attachment_names: list[str] = Field(default_factory=list)
    custom_rules: list[ValidationEvalCustomRule] = Field(default_factory=list)
    related_tasks: list[dict[str, Any]] = Field(default_factory=list)
    historical_questions: list[str] = Field(default_factory=list)
    expected_verdict: ValidationEvalVerdict
    expected_issues: list[ValidationEvalExpectedIssue] = Field(default_factory=list)
    expected_questions: list[str] = Field(default_factory=list)
    expected_context_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ValidationEvalCaseImport(ValidationEvalCaseBase):
    pass


class ValidationEvalCaseCreate(ValidationEvalCaseBase):
    pass


class ValidationEvalCaseUpdate(BaseModel):
    external_id: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None
    tags: list[str] | None = None
    attachment_names: list[str] | None = None
    custom_rules: list[ValidationEvalCustomRule] | None = None
    related_tasks: list[dict[str, Any]] | None = None
    historical_questions: list[str] | None = None
    expected_verdict: ValidationEvalVerdict | None = None
    expected_issues: list[ValidationEvalExpectedIssue] | None = None
    expected_questions: list[str] | None = None
    expected_context_questions: list[str] | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ValidationEvalStructuredImport(BaseModel):
    dataset_name: str = Field(min_length=3, max_length=255)
    project_id: str
    cases: list[ValidationEvalCaseImport] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ValidationEvalImportPayload(BaseModel):
    format: ValidationEvalImportFormat = "json"
    dataset_name: str | None = Field(default=None, min_length=3, max_length=255)
    project_id: str | None = None
    payload: ValidationEvalStructuredImport | None = None
    content: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def validate_utf8_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value.encode("utf-8")
        return value


class ValidationEvalVariantConfig(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=255)
    validation_node_settings: dict[str, bool] = Field(default_factory=dict)
    provider_config_id: str | None = None
    prompt_version_ids: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def _default_validation_eval_variants() -> list[ValidationEvalVariantConfig]:
    return [
        ValidationEvalVariantConfig(
            key="core_only",
            label="Core rules",
            validation_node_settings={
                "core_rules": True,
                "custom_rules": False,
                "context_questions": False,
            },
        ),
        ValidationEvalVariantConfig(
            key="core_custom",
            label="Core + custom rules",
            validation_node_settings={
                "core_rules": True,
                "custom_rules": True,
                "context_questions": False,
            },
        ),
        ValidationEvalVariantConfig(
            key="full",
            label="Full validation",
            validation_node_settings={
                "core_rules": True,
                "custom_rules": True,
                "context_questions": True,
            },
        ),
    ]


class ValidationEvalRunConfig(BaseModel):
    variants: list[ValidationEvalVariantConfig] = Field(
        default_factory=_default_validation_eval_variants,
        min_length=1,
    )
    run_question_judge: bool = True

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_unique_variants(self) -> ValidationEvalRunConfig:
        keys = [item.key for item in self.variants]
        if len(keys) != len(set(keys)):
            raise ValueError("Variant keys must be unique.")
        return self


class ValidationEvalDatasetRead(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    name: str
    cases_total: int
    last_run_id: str | None = None
    last_run_status: ValidationEvalRunStatus | None = None
    created_at: datetime
    updated_at: datetime


class ValidationEvalCaseRead(BaseModel):
    id: str
    external_id: str
    title: str
    content: str
    tags: list[str]
    attachment_names: list[str]
    custom_rules: list[dict[str, Any]]
    related_tasks: list[dict[str, Any]]
    historical_questions: list[str]
    expected_verdict: ValidationEvalVerdict
    expected_issues: list[dict[str, Any]]
    expected_questions: list[str]
    expected_context_questions: list[str]
    metadata: dict[str, Any]
    updated_at: datetime


class ValidationEvalDatasetDetailRead(ValidationEvalDatasetRead):
    cases: list[ValidationEvalCaseRead]


class ValidationEvalImportResultRead(BaseModel):
    dataset: ValidationEvalDatasetDetailRead
    imported_cases: int
    warnings: list[str] = Field(default_factory=list)


class ValidationEvalRunCreateRead(BaseModel):
    id: str
    dataset_id: str
    status: ValidationEvalRunStatus
    config: ValidationEvalRunConfig
    created_at: datetime


class ValidationEvalRunListItemRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: ValidationEvalRunStatus
    config: ValidationEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class ValidationEvalRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ValidationEvalRunListItemRead]


class ValidationEvalCaseResultRead(BaseModel):
    id: str
    case_id: str
    case_external_id: str
    variant_key: str
    variant_label: str | None
    status: ValidationEvalCaseResultStatus
    graph_run_id: str | None
    judge_graph_run_id: str | None
    expected_result: dict[str, Any]
    actual_result: dict[str, Any]
    diffs: dict[str, Any]
    judge_payload: dict[str, Any] | None
    metrics: dict[str, Any]
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class ValidationEvalRunRead(ValidationEvalRunListItemRead):
    case_results: list[ValidationEvalCaseResultRead] = Field(default_factory=list)
