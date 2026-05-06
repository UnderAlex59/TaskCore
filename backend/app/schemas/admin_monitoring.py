from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.admin_llm import PromptLogMode


MonitoringRange = Literal["24h", "7d", "30d", "90d"]
LLMRequestStatus = Literal["success", "error"]
GraphRunStatus = Literal["running", "success", "error"]


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
    graph_run_id: str | None
    graph_node_name: str | None
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


class GraphRunSummaryRead(BaseModel):
    range: MonitoringRange
    window_start: datetime
    runs_total: int
    success_total: int
    error_total: int
    running_total: int
    error_rate: float
    avg_latency_ms: float | None
    slowest_graphs: list[dict[str, int | float | str | None]]
    recent_failures: list[dict[str, str | int | None]]


class GraphRunListItemRead(BaseModel):
    id: str
    graph_key: str
    status: GraphRunStatus
    actor_name: str
    actor_user_id: str | None
    project_id: str | None
    task_id: str | None
    source: str | None
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    events_count: int
    llm_requests_count: int


class GraphRunPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[GraphRunListItemRead]


class GraphRunEventRead(BaseModel):
    id: str
    sequence: int
    event_type: str
    node_name: str | None
    namespace: str | None
    status: GraphRunStatus
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None
    payload: dict[str, Any] | None
    error_message: str | None


class GraphRunNodeRead(BaseModel):
    id: str
    sequence: int
    graph_key: str | None
    node_name: str
    namespace: str | None
    status: GraphRunStatus
    latency_ms: int | None
    input_preview: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    result_preview: dict[str, Any] | list[Any] | str | int | float | bool | None
    error_message: str | None
    llm_request_ids: list[str] = Field(default_factory=list)
    children: list["GraphRunNodeRead"] = Field(default_factory=list)


class GraphRunTransitionRead(BaseModel):
    id: str
    sequence: int
    graph_key: str | None
    namespace: str | None
    source_node: str | None
    condition: str | None
    reason: str | None = None
    condition_input_preview: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    selected: list[str]
    target_nodes: list[str]


class GraphRunGraphNodeRead(BaseModel):
    mermaid_id: str
    node_event_id: str | None = None
    node_name: str
    graph_key: str
    executed: bool


class GraphRunGraphViewRead(BaseModel):
    graph_key: str
    mermaid: str
    nodes: list[GraphRunGraphNodeRead] = Field(default_factory=list)
    executed_node_ids: list[str]
    executed_edge_ids: list[str] = Field(default_factory=list)
    selected_edge_ids: list[str]


class GraphRunDetailRead(BaseModel):
    id: str
    graph_key: str
    status: GraphRunStatus
    actor_name: str
    actor_user_id: str | None
    project_id: str | None
    task_id: str | None
    source: str | None
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None
    error_message: str | None
    input_preview: dict[str, Any] | None
    final_state_preview: dict[str, Any] | None
    events: list[GraphRunEventRead]
    node_tree: list[GraphRunNodeRead]
    transitions: list[GraphRunTransitionRead]
    graph_views: list[GraphRunGraphViewRead]
    llm_requests: list[LLMRequestLogRead]
