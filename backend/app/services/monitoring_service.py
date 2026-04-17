from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Select, case, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.audit_event import AuditEvent
from app.models.change_proposal import ChangeProposal
from app.models.llm_request_log import LLMRequestLog
from app.models.message import Message
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.admin_monitoring import (
    ActivityBucketRead,
    AuditEventRead,
    AuditPageRead,
    LLMProviderBreakdownRead,
    LLMDailyUsageRead,
    LLMRecentFailureRead,
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
