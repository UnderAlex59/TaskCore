from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.dependencies import DBSession, require_role
from app.models.task import TaskStatus
from app.models.user import User, UserRole
from app.schemas.admin_llm import (
    AgentOverrideRead,
    AgentOverrideUpdate,
    ProviderConfigPayload,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderTestResult,
    RuntimeDefaultProviderUpdate,
)
from app.schemas.admin_monitoring import (
    AuditPageRead,
    MonitoringActivityRead,
    MonitoringLLMRead,
    MonitoringRange,
    MonitoringSummaryRead,
)
from app.schemas.admin_validation import ValidationQuestionPageRead
from app.schemas.task_tag import AdminTaskTagRead, TaskTagCreate, TaskTagUpdate
from app.services.admin_llm_service import AdminLLMService
from app.services.monitoring_service import MonitoringService
from app.services.task_tag_service import TaskTagService
from app.services.validation_question_service import ValidationQuestionService

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


@router.get("/llm/providers", response_model=list[ProviderConfigRead])
async def list_llm_providers(
    _: AdminUser,
    db: DBSession,
) -> list[ProviderConfigRead]:
    return await AdminLLMService.list_provider_configs(db)


@router.post("/llm/providers", response_model=ProviderConfigRead, status_code=201)
async def create_llm_provider(
    payload: ProviderConfigPayload,
    current_user: AdminUser,
    db: DBSession,
) -> ProviderConfigRead:
    return await AdminLLMService.create_provider_config(payload, current_user, db)


@router.patch("/llm/providers/{provider_id}", response_model=ProviderConfigRead)
async def update_llm_provider(
    provider_id: str,
    payload: ProviderConfigUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> ProviderConfigRead:
    return await AdminLLMService.update_provider_config(provider_id, payload, current_user, db)


@router.post("/llm/providers/{provider_id}/test", response_model=ProviderTestResult)
async def test_llm_provider(
    provider_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> ProviderTestResult:
    return await AdminLLMService.test_provider_config(provider_id, current_user, db)


@router.post("/llm/runtime/default-provider", response_model=ProviderConfigRead)
async def set_default_llm_provider(
    payload: RuntimeDefaultProviderUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> ProviderConfigRead:
    return await AdminLLMService.set_default_provider(payload.provider_config_id, current_user, db)


@router.get("/llm/overrides", response_model=list[AgentOverrideRead])
async def list_llm_overrides(
    _: AdminUser,
    db: DBSession,
) -> list[AgentOverrideRead]:
    return await AdminLLMService.list_agent_overrides(db)


@router.put("/llm/overrides/{agent_key}", response_model=AgentOverrideRead)
async def update_llm_override(
    agent_key: str,
    payload: AgentOverrideUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> AgentOverrideRead:
    return await AdminLLMService.upsert_agent_override(agent_key, payload, current_user, db)


@router.get("/monitoring/summary", response_model=MonitoringSummaryRead)
async def monitoring_summary(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
) -> MonitoringSummaryRead:
    return await MonitoringService.get_summary(db, range_value=range_value)


@router.get("/monitoring/activity", response_model=MonitoringActivityRead)
async def monitoring_activity(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
) -> MonitoringActivityRead:
    return await MonitoringService.get_activity(db, range_value=range_value)


@router.get("/monitoring/llm", response_model=MonitoringLLMRead)
async def monitoring_llm(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
) -> MonitoringLLMRead:
    return await MonitoringService.get_llm_metrics(db, range_value=range_value)


@router.get("/audit", response_model=AuditPageRead)
async def audit_feed(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
    page: int = Query(default=1, ge=1),
) -> AuditPageRead:
    return await MonitoringService.get_audit_page(db, range_value=range_value, page=page)


@router.get("/validation/questions", response_model=ValidationQuestionPageRead)
async def list_validation_questions(
    _: AdminUser,
    db: DBSession,
    project_id: str | None = Query(default=None),
    task_status: TaskStatus | None = Query(default=None),
    verdict: Literal["approved", "needs_rework"] | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1),
    search: str | None = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> ValidationQuestionPageRead:
    return await ValidationQuestionService.list_questions(
        db,
        project_id=project_id,
        task_status=task_status,
        verdict=verdict,
        tag=tag,
        search=search,
        page=page,
        size=size,
    )


@router.delete("/validation/questions/{question_id}", status_code=204)
async def delete_validation_question(
    question_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> Response:
    await ValidationQuestionService.delete_question(question_id, current_user, db)
    return Response(status_code=204)


@router.get("/task-tags", response_model=list[AdminTaskTagRead])
async def list_task_tags(
    _: AdminUser,
    db: DBSession,
) -> list[AdminTaskTagRead]:
    return await TaskTagService.list_admin_task_tags(db)


@router.post("/task-tags", response_model=AdminTaskTagRead, status_code=status.HTTP_201_CREATED)
async def create_task_tag(
    payload: TaskTagCreate,
    current_user: AdminUser,
    db: DBSession,
) -> AdminTaskTagRead:
    return await TaskTagService.create_task_tag(payload, current_user, db)


@router.patch("/task-tags/{tag_id}", response_model=AdminTaskTagRead)
async def update_task_tag(
    tag_id: str,
    payload: TaskTagUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> AdminTaskTagRead:
    return await TaskTagService.update_task_tag(tag_id, payload, current_user, db)


@router.delete("/task-tags/{tag_id}", status_code=204)
async def delete_task_tag(
    tag_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> Response:
    await TaskTagService.delete_task_tag(tag_id, current_user, db)
    return Response(status_code=204)
