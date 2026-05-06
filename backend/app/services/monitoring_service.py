from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

from sqlalchemy import Select, case, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit_event import AuditEvent
from app.models.change_proposal import ChangeProposal
from app.models.graph_run_event import GraphRunEvent
from app.models.graph_run_log import GraphRunLog
from app.models.llm_request_log import LLMRequestLog
from app.models.llm_runtime_settings import LLMRuntimeSettings
from app.models.message import Message
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.agents.graph_export import get_graph_export_specs
from app.schemas.admin_llm import PromptLogMode
from app.schemas.admin_monitoring import (
    ActivityBucketRead,
    AuditEventRead,
    AuditPageRead,
    GraphRunDetailRead,
    GraphRunEventRead,
    GraphRunGraphNodeRead,
    GraphRunGraphViewRead,
    GraphRunListItemRead,
    GraphRunNodeRead,
    GraphRunPageRead,
    GraphRunStatus,
    GraphRunSummaryRead,
    GraphRunTransitionRead,
    LLMProviderBreakdownRead,
    LLMDailyUsageRead,
    LLMRecentFailureRead,
    LLMRequestLogPageRead,
    LLMRequestLogRead,
    LLMRequestStatus,
    MonitoringActivityRead,
    MonitoringAllTimeTotals,
    MonitoringLLMRead,
    MonitoringRange,
    MonitoringRangeMetrics,
    MonitoringSummaryRead,
    TopActionRead,
    TopActorRead,
)

RANGE_TO_DELTA: dict[MonitoringRange, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}

TASK_MUTATION_EVENTS = {
    "task.created",
    "task.updated",
    "task.deleted",
    "task.attachment_uploaded",
}

MERMAID_EDGE_PATTERN = re.compile(
    r"^\s*(?P<source>[A-Za-z_][\w]*)\b.*?(?:-->|==>|-.->|--x|--o).*?\b(?P<target>[A-Za-z_][\w]*)\b"
)


def _event_payload(event: GraphRunEvent) -> dict[str, object]:
    return event.payload if isinstance(event.payload, dict) else {}


def _payload_graph_key(event: GraphRunEvent, fallback: str) -> str | None:
    payload = _event_payload(event)
    value = payload.get("graph_key")
    if isinstance(value, str) and value:
        return value
    if event.namespace:
        return event.namespace.split(" / ")[-1]
    return fallback


def _payload_result(event: GraphRunEvent) -> object:
    payload = _event_payload(event)
    if "result_preview" in payload:
        return payload.get("result_preview")
    if "result" in payload:
        return payload.get("result")
    if event.node_name and event.node_name in payload:
        return payload.get(event.node_name)
    return payload


def _payload_input(event: GraphRunEvent) -> object | None:
    payload = _event_payload(event)
    if "input_preview" in payload:
        return payload.get("input_preview")
    if "input" in payload:
        return payload.get("input")
    return None


def _normalize_node_events(
    events: list[GraphRunEvent],
    *,
    root_graph_key: str,
    llm_request_ids_by_node: dict[str, list[str]] | None = None,
) -> list[GraphRunNodeRead]:
    node_events = [event for event in events if event.event_type == "node" and event.node_name]
    if not node_events:
        node_events = _collapse_legacy_node_events(events)

    llm_request_ids_by_node = llm_request_ids_by_node or {}
    roots: list[GraphRunNodeRead] = []
    node_index: dict[tuple[str | None, str], GraphRunNodeRead] = {}
    for event in node_events:
        if not event.node_name:
            continue
        graph_key = _payload_graph_key(event, root_graph_key)
        node = GraphRunNodeRead(
            id=event.id,
            sequence=event.sequence,
            graph_key=graph_key,
            node_name=event.node_name,
            namespace=event.namespace,
            status=cast(GraphRunStatus, event.status),
            latency_ms=event.latency_ms,
            input_preview=_payload_input(event),
            result_preview=_payload_result(event),
            error_message=event.error_message,
            llm_request_ids=llm_request_ids_by_node.get(event.node_name, []),
            children=[],
        )
        parent = _find_parent_node(node_index, event.namespace)
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
        node_index[(event.namespace, event.node_name)] = node
    return roots


def _collapse_legacy_node_events(events: list[GraphRunEvent]) -> list[GraphRunEvent]:
    collapsed: list[GraphRunEvent] = []
    seen: set[tuple[str | None, str]] = set()
    for event in events:
        if event.event_type == "debug" or not event.node_name:
            continue
        key = (event.namespace, event.node_name)
        if key in seen:
            continue
        seen.add(key)
        collapsed.append(event)
    return collapsed


def _find_parent_node(
    node_index: dict[tuple[str | None, str], GraphRunNodeRead],
    namespace: str | None,
) -> GraphRunNodeRead | None:
    if not namespace:
        return None
    parts = namespace.split(" / ")
    if len(parts) < 3:
        return None
    parent_namespace = " / ".join(parts[:-2])
    parent_node_name = parts[-2]
    return node_index.get((parent_namespace, parent_node_name))


def _normalize_transition_events(events: list[GraphRunEvent]) -> list[GraphRunTransitionRead]:
    transitions: list[GraphRunTransitionRead] = []
    for event in events:
        if event.event_type != "transition":
            continue
        payload = _event_payload(event)
        selected = payload.get("selected")
        target_nodes = payload.get("target_nodes")
        transitions.append(
            GraphRunTransitionRead(
                id=event.id,
                sequence=event.sequence,
                graph_key=payload.get("graph_key") if isinstance(payload.get("graph_key"), str) else None,
                namespace=event.namespace,
                source_node=payload.get("source_node") if isinstance(payload.get("source_node"), str) else event.node_name,
                condition=payload.get("condition") if isinstance(payload.get("condition"), str) else None,
                reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
                condition_input_preview=payload.get("condition_input_preview"),
                selected=[str(item) for item in selected] if isinstance(selected, list) else [],
                target_nodes=[str(item) for item in target_nodes] if isinstance(target_nodes, list) else [],
            )
        )
    return transitions


def _flatten_nodes(nodes: list[GraphRunNodeRead]) -> list[GraphRunNodeRead]:
    flattened: list[GraphRunNodeRead] = []

    def visit(items: list[GraphRunNodeRead]) -> None:
        for item in items:
            flattened.append(item)
            visit(item.children)

    visit(nodes)
    return flattened


def _collect_executed_by_graph(nodes: list[GraphRunNodeRead]) -> dict[str, set[str]]:
    executed: dict[str, set[str]] = {}

    for item in _flatten_nodes(nodes):
        if item.graph_key:
            executed.setdefault(item.graph_key, set()).add(item.node_name)
    return executed


def _collect_node_lookup(nodes: list[GraphRunNodeRead]) -> dict[tuple[str, str], GraphRunNodeRead]:
    lookup: dict[tuple[str, str], GraphRunNodeRead] = {}
    for item in _flatten_nodes(nodes):
        if item.graph_key:
            lookup.setdefault((item.graph_key, item.node_name), item)
    return lookup


def _extract_mermaid_edges(mermaid: str) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for line in mermaid.splitlines():
        match = MERMAID_EDGE_PATTERN.match(line)
        if not match:
            continue
        source = match.group("source")
        target = match.group("target")
        if source and target:
            edges.append((source, target))
    return edges


def _build_graph_views(
    *,
    node_tree: list[GraphRunNodeRead],
    transitions: list[GraphRunTransitionRead],
) -> list[GraphRunGraphViewRead]:
    specs = {spec.name: spec for spec in get_graph_export_specs()}
    executed_by_graph = _collect_executed_by_graph(node_tree)
    node_lookup = _collect_node_lookup(node_tree)
    selected_edges: dict[str, set[str]] = {}
    for transition in transitions:
        if not transition.graph_key or not transition.source_node:
            continue
        for target in transition.target_nodes:
            selected_edges.setdefault(transition.graph_key, set()).add(
                f"{transition.source_node}->{target}"
            )

    views: list[GraphRunGraphViewRead] = []
    for graph_key in sorted(executed_by_graph):
        spec = specs.get(graph_key)
        if spec is None:
            continue
        try:
            raw_mermaid = spec.factory().get_graph().draw_mermaid()
        except Exception:  # noqa: BLE001
            continue
        edge_pairs = _extract_mermaid_edges(raw_mermaid)
        graph_node_ids = set(executed_by_graph.get(graph_key, set()))
        for source, target in edge_pairs:
            graph_node_ids.add(source)
            graph_node_ids.add(target)
        executed_edges = {
            f"{source}->{target}"
            for source, target in edge_pairs
            if source in executed_by_graph.get(graph_key, set())
            and target in executed_by_graph.get(graph_key, set())
        }
        graph_selected_edges = selected_edges.get(graph_key, set())
        views.append(
            GraphRunGraphViewRead(
                graph_key=graph_key,
                mermaid=_highlight_mermaid(
                    raw_mermaid,
                    executed_nodes=executed_by_graph.get(graph_key, set()),
                    executed_edges=executed_edges,
                    selected_edges=graph_selected_edges,
                ),
                nodes=[
                    GraphRunGraphNodeRead(
                        mermaid_id=node_id,
                        node_event_id=(
                            node_lookup[(graph_key, node_id)].id
                            if (graph_key, node_id) in node_lookup
                            else None
                        ),
                        node_name=node_id,
                        graph_key=graph_key,
                        executed=node_id in executed_by_graph.get(graph_key, set()),
                    )
                    for node_id in sorted(graph_node_ids)
                ],
                executed_node_ids=sorted(executed_by_graph.get(graph_key, set())),
                executed_edge_ids=sorted(executed_edges),
                selected_edge_ids=sorted(graph_selected_edges),
            )
        )
    return views


def _highlight_mermaid(
    mermaid: str,
    *,
    executed_nodes: set[str],
    executed_edges: set[str],
    selected_edges: set[str],
) -> str:
    if not executed_nodes and not executed_edges and not selected_edges:
        return mermaid
    edge_indices: dict[str, list[int]] = {}
    for index, (source, target) in enumerate(_extract_mermaid_edges(mermaid)):
        edge_indices.setdefault(f"{source}->{target}", []).append(index)

    class_lines = [
        "classDef executed fill:#e9f2ff,stroke:#0c66e4,stroke-width:2px;",
    ]
    class_lines.extend(f"class {node} executed;" for node in sorted(executed_nodes))
    executed_indices = sorted(
        {
            index
            for edge_id in executed_edges - selected_edges
            for index in edge_indices.get(edge_id, [])
        }
    )
    selected_indices = sorted(
        {index for edge_id in selected_edges for index in edge_indices.get(edge_id, [])}
    )
    if executed_indices:
        class_lines.append(
            f"linkStyle {','.join(str(index) for index in executed_indices)} "
            "stroke:#6b778c,stroke-width:2px;"
        )
    if selected_indices:
        class_lines.append(
            f"linkStyle {','.join(str(index) for index in selected_indices)} "
            "stroke:#0c66e4,stroke-width:3px;"
        )
    return f"{mermaid.rstrip()}\n" + "\n".join(class_lines)


class MonitoringService:
    @staticmethod
    def _window_start(range_value: MonitoringRange) -> datetime:
        return datetime.now(timezone.utc) - RANGE_TO_DELTA[range_value]

    @staticmethod
    async def get_summary(db: AsyncSession, *, range_value: MonitoringRange) -> MonitoringSummaryRead:
        window_start = MonitoringService._window_start(range_value)

        all_time = MonitoringAllTimeTotals(
            users_total=await db.scalar(select(func.count()).select_from(User)) or 0,
            active_users_total=await db.scalar(
                select(func.count()).select_from(User).where(User.is_active.is_(True))
            )
            or 0,
            projects_total=await db.scalar(select(func.count()).select_from(Project)) or 0,
            tasks_total=await db.scalar(select(func.count()).select_from(Task)) or 0,
            messages_total=await db.scalar(select(func.count()).select_from(Message)) or 0,
            proposals_total=await db.scalar(select(func.count()).select_from(ChangeProposal)) or 0,
            validations_total=await db.scalar(
                select(func.count()).select_from(Task).where(Task.validation_result.is_not(None))
            )
            or 0,
        )

        llm_stmt = select(
            func.count().label("requests_total"),
            func.sum(case((LLMRequestLog.status == "error", 1), else_=0)).label("errors_total"),
            func.avg(LLMRequestLog.latency_ms).label("avg_latency_ms"),
            func.sum(LLMRequestLog.estimated_cost_usd).label("estimated_cost_usd"),
        ).where(LLMRequestLog.created_at >= window_start)
        llm_row = (await db.execute(llm_stmt)).one()
        llm_requests_total = int(llm_row.requests_total or 0)
        llm_errors_total = int(llm_row.errors_total or 0)

        range_metrics = MonitoringRangeMetrics(
            active_users=await db.scalar(
                select(func.count(distinct(AuditEvent.actor_user_id)))
                .where(
                    AuditEvent.created_at >= window_start,
                    AuditEvent.actor_user_id.is_not(None),
                )
            )
            or 0,
            audit_events_total=await db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at >= window_start)
            )
            or 0,
            llm_requests_total=llm_requests_total,
            llm_error_rate=(
                round(llm_errors_total / llm_requests_total, 4) if llm_requests_total else 0.0
            ),
            avg_llm_latency_ms=float(llm_row.avg_latency_ms) if llm_row.avg_latency_ms is not None else None,
            estimated_llm_cost_usd=llm_row.estimated_cost_usd,
        )
        return MonitoringSummaryRead(
            range=range_value,
            window_start=window_start,
            generated_at=datetime.now(timezone.utc),
            all_time=all_time,
            range_metrics=range_metrics,
        )

    @staticmethod
    async def get_activity(db: AsyncSession, *, range_value: MonitoringRange) -> MonitoringActivityRead:
        window_start = MonitoringService._window_start(range_value)
        day_bucket = func.date_trunc("day", AuditEvent.created_at)
        bucket_stmt = (
            select(
                day_bucket.label("day"),
                func.count().label("events_total"),
                func.sum(case((AuditEvent.event_type == "auth.login.success", 1), else_=0)).label("logins"),
                func.sum(case((AuditEvent.event_type.in_(TASK_MUTATION_EVENTS), 1), else_=0)).label(
                    "task_mutations"
                ),
                func.sum(case((AuditEvent.event_type == "task.validated", 1), else_=0)).label(
                    "validation_runs"
                ),
                func.sum(case((AuditEvent.event_type == "proposal.reviewed", 1), else_=0)).label(
                    "proposal_reviews"
                ),
                func.sum(case((AuditEvent.event_type.like("admin.%"), 1), else_=0)).label("admin_changes"),
            )
            .where(AuditEvent.created_at >= window_start)
            .group_by(day_bucket)
            .order_by(day_bucket.asc())
        )
        bucket_rows = list((await db.execute(bucket_stmt)).all())

        top_actor_stmt = (
            select(AuditEvent.actor_user_id, User.full_name, func.count().label("event_count"))
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.created_at >= window_start)
            .group_by(AuditEvent.actor_user_id, User.full_name)
            .order_by(desc("event_count"))
            .limit(5)
        )
        top_action_stmt = (
            select(AuditEvent.event_type, func.count().label("count"))
            .where(AuditEvent.created_at >= window_start)
            .group_by(AuditEvent.event_type)
            .order_by(desc("count"))
            .limit(5)
        )

        return MonitoringActivityRead(
            range=range_value,
            window_start=window_start,
            buckets=[
                ActivityBucketRead(
                    day=row.day.date().isoformat(),
                    events_total=int(row.events_total or 0),
                    logins=int(row.logins or 0),
                    task_mutations=int(row.task_mutations or 0),
                    validation_runs=int(row.validation_runs or 0),
                    proposal_reviews=int(row.proposal_reviews or 0),
                    admin_changes=int(row.admin_changes or 0),
                )
                for row in bucket_rows
            ],
            top_actors=[
                TopActorRead(
                    user_id=row.actor_user_id,
                    full_name=row.full_name or "Система",
                    event_count=int(row.event_count or 0),
                )
                for row in (await db.execute(top_actor_stmt)).all()
            ],
            top_actions=[
                TopActionRead(event_type=row.event_type, count=int(row.count or 0))
                for row in (await db.execute(top_action_stmt)).all()
            ],
        )

    @staticmethod
    async def get_llm_metrics(db: AsyncSession, *, range_value: MonitoringRange) -> MonitoringLLMRead:
        window_start = MonitoringService._window_start(range_value)
        summary_stmt = select(
            func.count().label("requests_total"),
            func.sum(case((LLMRequestLog.status == "success", 1), else_=0)).label("success_total"),
            func.sum(case((LLMRequestLog.status == "error", 1), else_=0)).label("error_total"),
            func.avg(LLMRequestLog.latency_ms).label("avg_latency_ms"),
            func.sum(LLMRequestLog.estimated_cost_usd).label("estimated_cost_usd"),
        ).where(LLMRequestLog.created_at >= window_start)
        summary_row = (await db.execute(summary_stmt)).one()

        provider_stmt = (
            select(LLMRequestLog.provider_kind, func.count().label("request_count"))
            .where(LLMRequestLog.created_at >= window_start)
            .group_by(LLMRequestLog.provider_kind)
            .order_by(desc("request_count"))
        )
        day_bucket = func.date_trunc("day", LLMRequestLog.created_at)
        daily_stmt = (
            select(
                day_bucket.label("day"),
                LLMRequestLog.provider_kind,
                func.count().label("request_count"),
            )
            .where(LLMRequestLog.created_at >= window_start)
            .group_by(day_bucket, LLMRequestLog.provider_kind)
            .order_by(day_bucket.asc())
        )

        actor = aliased(User)
        failure_stmt = (
            select(LLMRequestLog, actor.full_name)
            .outerjoin(actor, actor.id == LLMRequestLog.actor_user_id)
            .where(
                LLMRequestLog.created_at >= window_start,
                LLMRequestLog.status == "error",
            )
            .order_by(LLMRequestLog.created_at.desc())
            .limit(10)
        )

        daily_rows = list((await db.execute(daily_stmt)).all())
        daily_map: dict[str, dict[str, int]] = {}
        for row in daily_rows:
            day_key = row.day.date().isoformat()
            providers = daily_map.setdefault(day_key, {})
            providers[row.provider_kind] = int(row.request_count or 0)

        return MonitoringLLMRead(
            range=range_value,
            window_start=window_start,
            requests_total=int(summary_row.requests_total or 0),
            success_total=int(summary_row.success_total or 0),
            error_total=int(summary_row.error_total or 0),
            avg_latency_ms=float(summary_row.avg_latency_ms) if summary_row.avg_latency_ms is not None else None,
            estimated_cost_usd=summary_row.estimated_cost_usd,
            provider_breakdown=[
                LLMProviderBreakdownRead(
                    provider_kind=row.provider_kind,
                    request_count=int(row.request_count or 0),
                )
                for row in (await db.execute(provider_stmt)).all()
            ],
            daily=[
                LLMDailyUsageRead(
                    day=day,
                    total=sum(providers.values()),
                    providers=providers,
                )
                for day, providers in sorted(daily_map.items())
            ],
            recent_failures=[
                LLMRecentFailureRead(
                    id=log.id,
                    created_at=log.created_at,
                    agent_key=log.agent_key,
                    actor_name=full_name or "Система",
                    provider_kind=log.provider_kind,
                    model=log.model,
                    error_message=log.error_message,
                )
                for log, full_name in (await db.execute(failure_stmt)).all()
            ],
        )

    @staticmethod
    async def get_llm_request_page(
        db: AsyncSession,
        *,
        range_value: MonitoringRange,
        request_status: LLMRequestStatus | None,
        page: int,
        page_size: int = 20,
    ) -> LLMRequestLogPageRead:
        window_start = MonitoringService._window_start(range_value)
        conditions = [LLMRequestLog.created_at >= window_start]
        if request_status is not None:
            conditions.append(LLMRequestLog.status == request_status)

        runtime_settings = await db.get(LLMRuntimeSettings, 1)
        prompt_log_mode = (
            runtime_settings.prompt_log_mode if runtime_settings is not None else "full"
        )
        actor = aliased(User)
        total = await db.scalar(
            select(func.count()).select_from(LLMRequestLog).where(*conditions)
        )
        stmt: Select[tuple[LLMRequestLog, str | None]] = (
            select(LLMRequestLog, actor.full_name)
            .outerjoin(actor, actor.id == LLMRequestLog.actor_user_id)
            .where(*conditions)
            .order_by(LLMRequestLog.created_at.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).all())
        return LLMRequestLogPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            prompt_log_mode=cast(PromptLogMode, prompt_log_mode),
            items=[
                LLMRequestLogRead(
                    id=log.id,
                    created_at=log.created_at,
                    request_kind=log.request_kind,
                    actor_name=full_name or "Система",
                    task_id=log.task_id,
                    project_id=log.project_id,
                    agent_key=log.agent_key,
                    graph_run_id=log.graph_run_id,
                    graph_node_name=log.graph_node_name,
                    provider_kind=log.provider_kind,
                    model=log.model,
                    status=cast(LLMRequestStatus, log.status),
                    latency_ms=log.latency_ms,
                    prompt_tokens=log.prompt_tokens,
                    completion_tokens=log.completion_tokens,
                    total_tokens=log.total_tokens,
                    estimated_cost_usd=log.estimated_cost_usd,
                    request_messages=log.request_messages,
                    response_text=log.response_text,
                    error_message=log.error_message,
                )
                for log, full_name in rows
            ],
        )

    @staticmethod
    async def get_graph_run_summary(
        db: AsyncSession,
        *,
        range_value: MonitoringRange,
    ) -> GraphRunSummaryRead:
        window_start = MonitoringService._window_start(range_value)
        summary_stmt = select(
            func.count().label("runs_total"),
            func.sum(case((GraphRunLog.status == "success", 1), else_=0)).label("success_total"),
            func.sum(case((GraphRunLog.status == "error", 1), else_=0)).label("error_total"),
            func.sum(case((GraphRunLog.status == "running", 1), else_=0)).label("running_total"),
            func.avg(GraphRunLog.latency_ms).label("avg_latency_ms"),
        ).where(GraphRunLog.started_at >= window_start)
        row = (await db.execute(summary_stmt)).one()
        runs_total = int(row.runs_total or 0)
        error_total = int(row.error_total or 0)

        slowest_stmt = (
            select(
                GraphRunLog.graph_key,
                func.count().label("runs_total"),
                func.avg(GraphRunLog.latency_ms).label("avg_latency_ms"),
                func.max(GraphRunLog.latency_ms).label("max_latency_ms"),
            )
            .where(GraphRunLog.started_at >= window_start)
            .group_by(GraphRunLog.graph_key)
            .order_by(desc("avg_latency_ms"))
            .limit(8)
        )
        failures_stmt = (
            select(GraphRunLog)
            .where(GraphRunLog.started_at >= window_start, GraphRunLog.status == "error")
            .order_by(GraphRunLog.started_at.desc())
            .limit(10)
        )
        return GraphRunSummaryRead(
            range=range_value,
            window_start=window_start,
            runs_total=runs_total,
            success_total=int(row.success_total or 0),
            error_total=error_total,
            running_total=int(row.running_total or 0),
            error_rate=round(error_total / runs_total, 4) if runs_total else 0.0,
            avg_latency_ms=float(row.avg_latency_ms) if row.avg_latency_ms is not None else None,
            slowest_graphs=[
                {
                    "graph_key": item.graph_key,
                    "runs_total": int(item.runs_total or 0),
                    "avg_latency_ms": float(item.avg_latency_ms) if item.avg_latency_ms is not None else None,
                    "max_latency_ms": int(item.max_latency_ms or 0) if item.max_latency_ms is not None else None,
                }
                for item in (await db.execute(slowest_stmt)).all()
            ],
            recent_failures=[
                {
                    "id": item.id,
                    "graph_key": item.graph_key,
                    "task_id": item.task_id,
                    "project_id": item.project_id,
                    "latency_ms": item.latency_ms,
                    "error_message": item.error_message,
                    "started_at": item.started_at.isoformat(),
                }
                for item in (await db.scalars(failures_stmt)).all()
            ],
        )

    @staticmethod
    async def get_graph_run_page(
        db: AsyncSession,
        *,
        range_value: MonitoringRange,
        run_status: GraphRunStatus | None,
        graph_key: str | None,
        project_id: str | None,
        task_id: str | None,
        page: int,
        page_size: int = 20,
    ) -> GraphRunPageRead:
        window_start = MonitoringService._window_start(range_value)
        conditions = [GraphRunLog.started_at >= window_start]
        if run_status is not None:
            conditions.append(GraphRunLog.status == run_status)
        if graph_key:
            conditions.append(GraphRunLog.graph_key == graph_key)
        if project_id:
            conditions.append(GraphRunLog.project_id == project_id)
        if task_id:
            conditions.append(GraphRunLog.task_id == task_id)

        total = await db.scalar(select(func.count()).select_from(GraphRunLog).where(*conditions))
        actor = aliased(User)
        events_count = (
            select(GraphRunEvent.graph_run_id, func.count().label("events_total"))
            .where(GraphRunEvent.event_type == "node")
            .group_by(GraphRunEvent.graph_run_id)
            .subquery()
        )
        llm_count = (
            select(LLMRequestLog.graph_run_id, func.count().label("llm_total"))
            .where(LLMRequestLog.graph_run_id.is_not(None))
            .group_by(LLMRequestLog.graph_run_id)
            .subquery()
        )
        stmt = (
            select(
                GraphRunLog,
                actor.full_name,
                events_count.c.events_total,
                llm_count.c.llm_total,
            )
            .outerjoin(actor, actor.id == GraphRunLog.actor_user_id)
            .outerjoin(events_count, events_count.c.graph_run_id == GraphRunLog.id)
            .outerjoin(llm_count, llm_count.c.graph_run_id == GraphRunLog.id)
            .where(*conditions)
            .order_by(GraphRunLog.started_at.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        return GraphRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                GraphRunListItemRead(
                    id=run.id,
                    graph_key=run.graph_key,
                    status=cast(GraphRunStatus, run.status),
                    actor_name=full_name or "Система",
                    actor_user_id=run.actor_user_id,
                    project_id=run.project_id,
                    task_id=run.task_id,
                    source=run.source,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    latency_ms=run.latency_ms,
                    error_message=run.error_message,
                    events_count=int(events_total or 0),
                    llm_requests_count=int(llm_total or 0),
                )
                for run, full_name, events_total, llm_total in (await db.execute(stmt)).all()
            ],
        )

    @staticmethod
    async def get_graph_run_detail(db: AsyncSession, *, run_id: str) -> GraphRunDetailRead:
        actor = aliased(User)
        row = (
            await db.execute(
                select(GraphRunLog, actor.full_name)
                .outerjoin(actor, actor.id == GraphRunLog.actor_user_id)
                .where(GraphRunLog.id == run_id)
            )
        ).first()
        if row is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запуск графа не найден.")
        run, full_name = row
        events = list(
            (
                await db.scalars(
                    select(GraphRunEvent)
                    .where(GraphRunEvent.graph_run_id == run.id)
                    .order_by(GraphRunEvent.sequence.asc())
                )
            ).all()
        )
        llm_rows = list(
            (
                await db.execute(
                    select(LLMRequestLog, actor.full_name)
                    .outerjoin(actor, actor.id == LLMRequestLog.actor_user_id)
                    .where(LLMRequestLog.graph_run_id == run.id)
                    .order_by(LLMRequestLog.created_at.asc())
                )
            ).all()
        )
        llm_request_ids_by_node: dict[str, list[str]] = {}
        for log, _ in llm_rows:
            if log.graph_node_name:
                llm_request_ids_by_node.setdefault(log.graph_node_name, []).append(log.id)
        node_tree = _normalize_node_events(
            events,
            root_graph_key=run.graph_key,
            llm_request_ids_by_node=llm_request_ids_by_node,
        )
        transitions = _normalize_transition_events(events)
        return GraphRunDetailRead(
            id=run.id,
            graph_key=run.graph_key,
            status=cast(GraphRunStatus, run.status),
            actor_name=full_name or "Система",
            actor_user_id=run.actor_user_id,
            project_id=run.project_id,
            task_id=run.task_id,
            source=run.source,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            input_preview=run.input_preview,
            final_state_preview=run.final_state_preview,
            events=[
                GraphRunEventRead(
                    id=event.id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    node_name=event.node_name,
                    namespace=event.namespace,
                    status=cast(GraphRunStatus, event.status),
                    started_at=event.started_at,
                    finished_at=event.finished_at,
                    latency_ms=event.latency_ms,
                    payload=event.payload,
                    error_message=event.error_message,
                )
                for event in events
            ],
            node_tree=node_tree,
            transitions=transitions,
            graph_views=_build_graph_views(
                node_tree=node_tree,
                transitions=transitions,
            ),
            llm_requests=[
                LLMRequestLogRead(
                    id=log.id,
                    created_at=log.created_at,
                    request_kind=log.request_kind,
                    actor_name=llm_actor_name or "Система",
                    task_id=log.task_id,
                    project_id=log.project_id,
                    agent_key=log.agent_key,
                    graph_run_id=log.graph_run_id,
                    graph_node_name=log.graph_node_name,
                    provider_kind=log.provider_kind,
                    model=log.model,
                    status=cast(LLMRequestStatus, log.status),
                    latency_ms=log.latency_ms,
                    prompt_tokens=log.prompt_tokens,
                    completion_tokens=log.completion_tokens,
                    total_tokens=log.total_tokens,
                    estimated_cost_usd=log.estimated_cost_usd,
                    request_messages=log.request_messages,
                    response_text=log.response_text,
                    error_message=log.error_message,
                )
                for log, llm_actor_name in llm_rows
            ],
        )

    @staticmethod
    async def get_audit_page(
        db: AsyncSession,
        *,
        range_value: MonitoringRange,
        page: int,
        page_size: int = 20,
    ) -> AuditPageRead:
        window_start = MonitoringService._window_start(range_value)
        actor = aliased(User)
        total = await db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at >= window_start)
        )
        stmt: Select[tuple[AuditEvent, str | None]] = (
            select(AuditEvent, actor.full_name)
            .outerjoin(actor, actor.id == AuditEvent.actor_user_id)
            .where(AuditEvent.created_at >= window_start)
            .order_by(AuditEvent.created_at.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).all())
        return AuditPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                AuditEventRead(
                    id=event.id,
                    created_at=event.created_at,
                    actor_name=full_name or "Система",
                    event_type=event.event_type,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    project_id=event.project_id,
                    task_id=event.task_id,
                    metadata=event.payload,
                )
                for event, full_name in rows
            ],
        )
