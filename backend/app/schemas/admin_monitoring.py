from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.admin_llm import PromptLogMode


MonitoringRange = Literal["24h", "7d", "30d", "90d"]
LLMRequestStatus = Literal["success", "error"]


class MonitoringAllTimeTotals(BaseModel):
    users_total: int
    active_users_total: int
    projects_total: int
    tasks_total: int
    messages_total: int
    proposals_total: int
    validations_total: int


class MonitoringRangeMetrics(BaseModel):
    active_users: int
    audit_events_total: int
    llm_requests_total: int
    llm_error_rate: float
    avg_llm_latency_ms: float | None
    estimated_llm_cost_usd: Decimal | None


class MonitoringSummaryRead(BaseModel):
    range: MonitoringRange
    window_start: datetime
    generated_at: datetime
    all_time: MonitoringAllTimeTotals
    range_metrics: MonitoringRangeMetrics


class ActivityBucketRead(BaseModel):
    day: str
    events_total: int
    logins: int
    task_mutations: int
    validation_runs: int
    proposal_reviews: int
    admin_changes: int


class TopActorRead(BaseModel):
    user_id: str | None
    full_name: str
    event_count: int


class TopActionRead(BaseModel):
    event_type: str
    count: int


class MonitoringActivityRead(BaseModel):
    range: MonitoringRange
    window_start: datetime
    buckets: list[ActivityBucketRead]
    top_actors: list[TopActorRead]
    top_actions: list[TopActionRead]


class LLMProviderBreakdownRead(BaseModel):
    provider_kind: str
    request_count: int


class LLMDailyUsageRead(BaseModel):
    day: str
    total: int
    providers: dict[str, int]


class LLMRecentFailureRead(BaseModel):
    id: str
    created_at: datetime
    agent_key: str | None
    actor_name: str
    provider_kind: str
    model: str
    error_message: str | None


class MonitoringLLMRead(BaseModel):
    range: MonitoringRange
    window_start: datetime
    requests_total: int
    success_total: int
    error_total: int
    avg_latency_ms: float | None
    estimated_cost_usd: Decimal | None
    provider_breakdown: list[LLMProviderBreakdownRead]
    daily: list[LLMDailyUsageRead]
    recent_failures: list[LLMRecentFailureRead]


class LLMRequestLogRead(BaseModel):
    id: str
    created_at: datetime
    request_kind: str
    actor_name: str
    task_id: str | None
    project_id: str | None
    agent_key: str | None
    provider_kind: str
    model: str
    status: LLMRequestStatus
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: Decimal | None
    request_messages: list[dict[str, Any]] | None
    response_text: str | None
    error_message: str | None


class LLMRequestLogPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    prompt_log_mode: PromptLogMode
    items: list[LLMRequestLogRead]


class AuditEventRead(BaseModel):
    id: str
    created_at: datetime
    actor_name: str
    event_type: str
    entity_type: str
    entity_id: str | None
    project_id: str | None
    task_id: str | None
    metadata: dict | None


class AuditPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[AuditEventRead]
