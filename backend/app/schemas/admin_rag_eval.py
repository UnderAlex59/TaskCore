from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RagEvalImportFormat = Literal["json", "csv"]
RagEvalIndexingMode = Literal["all", "stale_only", "none"]
RagEvalRunStatus = Literal["queued", "running", "success", "error"]
RagEvalCaseStatus = Literal["success", "error"]
RagEvalGroundedness = Literal["grounded", "partially_grounded", "unsupported"]
RagEvalCorrectness = Literal["correct", "partially_correct", "incorrect", "not_enough_context"]


class RagEvalAttachmentImport(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(default="text/plain", max_length=100)
    content: str

    model_config = ConfigDict(extra="forbid")


class RagEvalTaskImport(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=3, max_length=500)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    attachments: list[RagEvalAttachmentImport] | None = None

    model_config = ConfigDict(extra="forbid")


class RagEvalExpectedRelevant(BaseModel):
    task_external_id: str | None = Field(default=None, max_length=255)
    source_type: str | None = Field(default=None, max_length=100)
    chunk_index: int | None = Field(default=None, ge=0)
    text_contains: str | None = None

    model_config = ConfigDict(extra="forbid")


class RagEvalCaseImport(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    task_external_id: str = Field(min_length=1, max_length=255)
    question: str = Field(min_length=1)
    expected_answer: str | None = None
    expected_relevant: list[RagEvalExpectedRelevant] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RagEvalStructuredImport(BaseModel):
    dataset_name: str = Field(min_length=3, max_length=255)
    project_id: str
    tasks: list[RagEvalTaskImport] = Field(default_factory=list)
    cases: list[RagEvalCaseImport] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RagEvalImportPayload(BaseModel):
    format: RagEvalImportFormat = "json"
    dataset_id: str | None = None
    dataset_name: str | None = Field(default=None, min_length=3, max_length=255)
    project_id: str | None = None
    payload: RagEvalStructuredImport | None = None
    content: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def validate_utf8_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value.encode("utf-8")
        return value


class RagEvalRunConfig(BaseModel):
    indexing_mode: RagEvalIndexingMode = "all"
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    use_query_rewriter: bool = True
    use_hybrid_rerank: bool = True
    include_cross_task: bool = True
    include_current_task_content: bool = False
    run_answer_agent: bool = True
    run_llm_judge: bool = True
    judge_provider_config_ids: list[str] = Field(default_factory=list)
    run_bm25_baseline: bool = True
    min_score_override: float | None = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("judge_provider_config_ids")
    @classmethod
    def validate_judge_provider_config_ids(cls, value: list[str]) -> list[str]:
        ids = [item.strip() for item in value if item.strip()]
        if not ids:
            return []
        if len(ids) > 3:
            raise ValueError("Judge provider list must be empty or contain 1 to 3 ids.")
        if len(set(ids)) != len(ids):
            raise ValueError("Judge provider ids must be unique.")
        return ids


class RagEvalDatasetTaskRead(BaseModel):
    id: str
    external_id: str
    task_id: str
    title: str
    updated_at: datetime


class RagEvalCaseRead(BaseModel):
    id: str
    external_id: str
    task_external_id: str
    task_id: str
    question: str
    expected_answer: str | None
    expected_relevant: list[dict[str, Any]]
    updated_at: datetime


class RagEvalDatasetRead(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    name: str
    tasks_total: int
    cases_total: int
    last_run_id: str | None = None
    last_run_status: RagEvalRunStatus | None = None
    created_at: datetime
    updated_at: datetime


class RagEvalDatasetDetailRead(RagEvalDatasetRead):
    tasks: list[RagEvalDatasetTaskRead]
    cases: list[RagEvalCaseRead]


class RagEvalImportResultRead(BaseModel):
    dataset: RagEvalDatasetDetailRead
    created_tasks: int
    updated_tasks: int
    imported_cases: int
    warnings: list[str] = Field(default_factory=list)


class RagEvalIndexResultRead(BaseModel):
    id: str
    task_id: str
    task_external_id: str
    status: str
    attachment_payload_ms: int | None
    chunking_ms: int | None
    embedding_and_qdrant_write_ms: int | None
    qdrant_cleanup_ms: int | None
    total_index_ms: int | None
    chunks_total: int
    error_message: str | None
    created_at: datetime


class RagEvalCaseResultRead(BaseModel):
    id: str
    case_id: str
    case_external_id: str
    question: str
    task_id: str
    task_external_id: str
    status: str
    retrieved_chunks: list[dict[str, Any]]
    matched_expected: list[dict[str, Any]]
    answer_text: str | None
    answer_source_ref: dict[str, Any] | None
    judge_payload: dict[str, Any] | None
    metrics: dict[str, Any]
    latency_ms: int | None
    retrieval_latency_ms: int | None
    answer_latency_ms: int | None
    judge_latency_ms: int | None
    error_message: str | None
    created_at: datetime


class RagEvalRunRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: RagEvalRunStatus
    config: RagEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    index_results: list[RagEvalIndexResultRead] = Field(default_factory=list)
    case_results: list[RagEvalCaseResultRead] = Field(default_factory=list)


class RagEvalRunCreateRead(BaseModel):
    id: str
    dataset_id: str
    status: RagEvalRunStatus
    config: RagEvalRunConfig
    created_at: datetime


class RagEvalRunListItemRead(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str | None = None
    project_id: str
    status: RagEvalRunStatus
    config: RagEvalRunConfig
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class RagEvalRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[RagEvalRunListItemRead]


class RagEvalJudgeResult(BaseModel):
    groundedness: RagEvalGroundedness
    correctness: RagEvalCorrectness
    unsupported_claims: list[str] = Field(default_factory=list)
    rationale: str = ""


class RagEvalCostSummary(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal | None
