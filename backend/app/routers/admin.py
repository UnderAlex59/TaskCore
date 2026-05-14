from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Response, UploadFile, status

from app.core.dependencies import DBSession, require_role
from app.models.task import TaskStatus
from app.models.user import User, UserRole
from app.schemas.admin_llm import (
    AgentDirectoryRead,
    AgentOverrideRead,
    AgentOverrideUpdate,
    AgentPromptConfigRead,
    AgentPromptRestorePayload,
    AgentPromptUpdate,
    AgentPromptVersionRead,
    ProviderConfigPayload,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderTestResult,
    RuntimeDefaultProviderUpdate,
    RuntimeSettingsRead,
    RuntimeSettingsUpdate,
    VisionTestResult,
)
from app.schemas.admin_monitoring import (
    AuditPageRead,
    GraphRunDetailRead,
    GraphRunPageRead,
    GraphRunStatus,
    GraphRunSummaryRead,
    LLMRequestLogPageRead,
    LLMRequestStatus,
    MonitoringActivityRead,
    MonitoringLLMRead,
    MonitoringRange,
    MonitoringSummaryRead,
)
from app.schemas.admin_qdrant import (
    QdrantDuplicateProposalProbePayload,
    QdrantOverviewRead,
    QdrantProjectCoverageRead,
    QdrantProjectQuestionsProbePayload,
    QdrantQaRagChunksProbePayload,
    QdrantRelatedTasksProbePayload,
    QdrantScenarioProbeRead,
    QdrantTaskResyncRead,
)
from app.schemas.admin_rag_eval import (
    RagEvalDatasetDetailRead,
    RagEvalDatasetRead,
    RagEvalImportPayload,
    RagEvalImportResultRead,
    RagEvalRunConfig,
    RagEvalRunCreateRead,
    RagEvalRunPageRead,
    RagEvalRunRead,
    RagEvalRunStatus,
)
from app.schemas.admin_validation import ValidationQuestionPageRead
from app.schemas.task_tag import AdminTaskTagRead, TaskTagCreate, TaskTagUpdate
from app.services.admin_llm_service import AdminLLMService
from app.services.admin_qdrant_service import AdminQdrantService
from app.services.admin_rag_eval_service import AdminRagEvalService
from app.services.llm_prompt_service import LLMPromptService
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


@router.post("/llm/vision-test", response_model=VisionTestResult)
async def test_llm_vision(
    current_user: AdminUser,
    db: DBSession,
    file: UploadFile = File(...),
    prompt: str = Form(...),
) -> VisionTestResult:
    return await AdminLLMService.test_vision_payload(
        filename=file.filename or "attachment",
        content_type=file.content_type,
        image_bytes=await file.read(),
        prompt=prompt,
        actor=current_user,
        db=db,
    )


@router.post("/llm/runtime/default-provider", response_model=ProviderConfigRead)
async def set_default_llm_provider(
    payload: RuntimeDefaultProviderUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> ProviderConfigRead:
    return await AdminLLMService.set_default_provider(payload.provider_config_id, current_user, db)


@router.get("/llm/runtime/settings", response_model=RuntimeSettingsRead)
async def get_llm_runtime_settings(
    _: AdminUser,
    db: DBSession,
) -> RuntimeSettingsRead:
    return await AdminLLMService.get_runtime_settings(db)


@router.patch("/llm/runtime/settings", response_model=RuntimeSettingsRead)
async def update_llm_runtime_settings(
    payload: RuntimeSettingsUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> RuntimeSettingsRead:
    return await AdminLLMService.update_runtime_settings(payload, current_user, db)


@router.get("/llm/overrides", response_model=list[AgentOverrideRead])
async def list_llm_overrides(
    _: AdminUser,
    db: DBSession,
) -> list[AgentOverrideRead]:
    return await AdminLLMService.list_agent_overrides(db)


@router.get("/llm/agents", response_model=list[AgentDirectoryRead])
async def list_llm_agents(
    _: AdminUser,
) -> list[AgentDirectoryRead]:
    return await AdminLLMService.list_available_agents()


@router.put("/llm/overrides/{agent_key}", response_model=AgentOverrideRead)
async def update_llm_override(
    agent_key: str,
    payload: AgentOverrideUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> AgentOverrideRead:
    return await AdminLLMService.upsert_agent_override(agent_key, payload, current_user, db)


@router.get("/llm/prompt-configs", response_model=list[AgentPromptConfigRead])
async def list_llm_prompt_configs(
    _: AdminUser,
    db: DBSession,
) -> list[AgentPromptConfigRead]:
    return await LLMPromptService.list_prompt_configs(db)


@router.patch("/llm/prompt-configs/{prompt_key}", response_model=AgentPromptConfigRead)
async def update_llm_prompt_config(
    prompt_key: str,
    payload: AgentPromptUpdate,
    current_user: AdminUser,
    db: DBSession,
) -> AgentPromptConfigRead:
    return await LLMPromptService.update_prompt_config(prompt_key, payload, current_user, db)


@router.get(
    "/llm/prompt-configs/{prompt_key}/versions",
    response_model=list[AgentPromptVersionRead],
)
async def list_llm_prompt_versions(
    prompt_key: str,
    _: AdminUser,
    db: DBSession,
) -> list[AgentPromptVersionRead]:
    return await LLMPromptService.list_prompt_versions(prompt_key, db)


@router.post("/llm/prompt-configs/{prompt_key}/restore", response_model=AgentPromptConfigRead)
async def restore_llm_prompt_version(
    prompt_key: str,
    payload: AgentPromptRestorePayload,
    current_user: AdminUser,
    db: DBSession,
) -> AgentPromptConfigRead:
    return await LLMPromptService.restore_prompt_version(
        prompt_key,
        payload.version_id,
        current_user,
        db,
    )


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


@router.get("/qdrant/overview", response_model=QdrantOverviewRead)
async def qdrant_overview(_: AdminUser) -> QdrantOverviewRead:
    return await AdminQdrantService.get_overview()


@router.get("/qdrant/projects/{project_id}/coverage", response_model=QdrantProjectCoverageRead)
async def qdrant_project_coverage(
    project_id: str,
    _: AdminUser,
    db: DBSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> QdrantProjectCoverageRead:
    return await AdminQdrantService.get_project_coverage(project_id, db, limit=limit)


@router.post("/qdrant/scenarios/related-tasks", response_model=QdrantScenarioProbeRead)
async def qdrant_probe_related_tasks(
    payload: QdrantRelatedTasksProbePayload,
    _: AdminUser,
    db: DBSession,
) -> QdrantScenarioProbeRead:
    return await AdminQdrantService.probe_related_tasks(payload, db)


@router.post("/qdrant/scenarios/project-questions", response_model=QdrantScenarioProbeRead)
async def qdrant_probe_project_questions(
    payload: QdrantProjectQuestionsProbePayload,
    _: AdminUser,
    db: DBSession,
) -> QdrantScenarioProbeRead:
    return await AdminQdrantService.probe_project_questions(payload, db)


@router.post("/qdrant/scenarios/qa-rag-chunks", response_model=QdrantScenarioProbeRead)
async def qdrant_probe_qa_rag_chunks(
    payload: QdrantQaRagChunksProbePayload,
    _: AdminUser,
    db: DBSession,
) -> QdrantScenarioProbeRead:
    return await AdminQdrantService.probe_qa_rag_chunks(payload, db)


@router.post("/qdrant/scenarios/duplicate-proposal", response_model=QdrantScenarioProbeRead)
async def qdrant_probe_duplicate_proposal(
    payload: QdrantDuplicateProposalProbePayload,
    _: AdminUser,
    db: DBSession,
) -> QdrantScenarioProbeRead:
    return await AdminQdrantService.probe_duplicate_proposal(payload, db)


@router.post("/qdrant/tasks/{task_id}/resync", response_model=QdrantTaskResyncRead)
async def qdrant_resync_task(
    task_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> QdrantTaskResyncRead:
    return await AdminQdrantService.resync_task(task_id, current_user, db)


@router.get("/rag-eval/datasets", response_model=list[RagEvalDatasetRead])
async def list_rag_eval_datasets(
    _: AdminUser,
    db: DBSession,
) -> list[RagEvalDatasetRead]:
    return await AdminRagEvalService.list_datasets(db)


@router.post("/rag-eval/datasets/import", response_model=RagEvalImportResultRead, status_code=201)
async def import_rag_eval_dataset(
    payload: RagEvalImportPayload,
    current_user: AdminUser,
    db: DBSession,
) -> RagEvalImportResultRead:
    return await AdminRagEvalService.import_dataset(payload, current_user, db)


@router.get("/rag-eval/datasets/{dataset_id}", response_model=RagEvalDatasetDetailRead)
async def get_rag_eval_dataset(
    dataset_id: str,
    _: AdminUser,
    db: DBSession,
) -> RagEvalDatasetDetailRead:
    return await AdminRagEvalService.get_dataset(dataset_id, db)


@router.get("/rag-eval/datasets/{dataset_id}/runs", response_model=RagEvalRunPageRead)
async def list_rag_eval_runs(
    dataset_id: str,
    _: AdminUser,
    db: DBSession,
    run_status: RagEvalRunStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
) -> RagEvalRunPageRead:
    return await AdminRagEvalService.list_runs(
        dataset_id,
        db,
        run_status=run_status,
        page=page,
        page_size=size,
    )


@router.post("/rag-eval/datasets/{dataset_id}/runs", response_model=RagEvalRunCreateRead, status_code=201)
async def create_rag_eval_run(
    dataset_id: str,
    payload: RagEvalRunConfig,
    background_tasks: BackgroundTasks,
    current_user: AdminUser,
    db: DBSession,
) -> RagEvalRunCreateRead:
    run = await AdminRagEvalService.create_run(dataset_id, payload, current_user, db)
    background_tasks.add_task(AdminRagEvalService.process_run, run.id)
    return run


@router.get("/rag-eval/runs/{run_id}", response_model=RagEvalRunRead)
async def get_rag_eval_run(
    run_id: str,
    _: AdminUser,
    db: DBSession,
) -> RagEvalRunRead:
    return await AdminRagEvalService.get_run(run_id, db)


@router.delete("/rag-eval/runs/{run_id}", status_code=204)
async def delete_rag_eval_run(
    run_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> Response:
    await AdminRagEvalService.delete_run(run_id, current_user, db)
    return Response(status_code=204)


@router.get("/rag-eval/runs/{run_id}/export")
async def export_rag_eval_run(
    run_id: str,
    _: AdminUser,
    db: DBSession,
    export_format: str = Query(default="json", alias="format"),
) -> Response:
    filename, media_type, content = await AdminRagEvalService.export_run(run_id, export_format, db)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/rag-eval/datasets/{dataset_id}", status_code=204)
async def delete_rag_eval_dataset(
    dataset_id: str,
    current_user: AdminUser,
    db: DBSession,
) -> Response:
    await AdminRagEvalService.delete_dataset(dataset_id, current_user, db)
    return Response(status_code=204)


@router.get("/monitoring/llm/requests", response_model=LLMRequestLogPageRead)
async def monitoring_llm_requests(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
    request_status: LLMRequestStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
) -> LLMRequestLogPageRead:
    return await MonitoringService.get_llm_request_page(
        db,
        range_value=range_value,
        request_status=request_status,
        page=page,
        page_size=size,
    )


@router.get("/monitoring/graphs/summary", response_model=GraphRunSummaryRead)
async def monitoring_graph_summary(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
) -> GraphRunSummaryRead:
    return await MonitoringService.get_graph_run_summary(db, range_value=range_value)


@router.get("/monitoring/graphs/runs", response_model=GraphRunPageRead)
async def monitoring_graph_runs(
    _: AdminUser,
    db: DBSession,
    range_value: MonitoringRange = Query(default="7d", alias="range"),
    run_status: GraphRunStatus | None = Query(default=None, alias="status"),
    graph_key: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
) -> GraphRunPageRead:
    return await MonitoringService.get_graph_run_page(
        db,
        range_value=range_value,
        run_status=run_status,
        graph_key=graph_key,
        project_id=project_id,
        task_id=task_id,
        page=page,
        page_size=size,
    )


@router.get("/monitoring/graphs/runs/{run_id}", response_model=GraphRunDetailRead)
async def monitoring_graph_run_detail(
    run_id: str,
    _: AdminUser,
    db: DBSession,
) -> GraphRunDetailRead:
    return await MonitoringService.get_graph_run_detail(db, run_id=run_id)


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
