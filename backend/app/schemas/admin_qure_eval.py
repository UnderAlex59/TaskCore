from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

QureEvalRunStatus = Literal["queued", "running", "success", "error"]
QureEvalCaseResultStatus = Literal["queued", "passed", "failed", "error"]


class QureEvalRunCreateRead(BaseModel):
    id: str
    project_id: str
    status: QureEvalRunStatus
    row_limit: int
    total_rows: int
    selected_rows: int
    selection_strategy: str
    created_at: datetime


class QureEvalRunListItemRead(BaseModel):
    id: str
    project_id: str
    project_name: str | None = None
    filename: str
    file_sha256: str
    row_limit: int
    selection_strategy: str
    total_rows: int
    selected_rows: int
    status: QureEvalRunStatus
    summary_metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class QureEvalRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[QureEvalRunListItemRead]


class QureEvalCaseResultRead(BaseModel):
    id: str
    run_id: str
    graph_run_id: str | None
    judge_graph_run_id: str | None
    row_index: int
    source_id: str
    requirement: str
    defect: Literal["ok", "defect"]
    weak_word: str
    expected_verdict: Literal["approved", "needs_rework"]
    actual_result: dict[str, Any]
    judge_payload: dict[str, Any] | None
    metrics: dict[str, Any]
    status: QureEvalCaseResultStatus
    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class QureEvalRunRead(QureEvalRunListItemRead):
    case_results: list[QureEvalCaseResultRead] = Field(default_factory=list)
