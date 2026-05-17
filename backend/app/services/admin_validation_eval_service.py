from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from time import perf_counter
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.system_prompts import (
    VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
    VALIDATION_CORE_PROMPT_KEY,
    VALIDATION_CUSTOM_RULES_PROMPT_KEY,
)
from app.agents.validation_eval_question_judge_graph import (
    run_validation_eval_question_judge_graph,
)
from app.agents.validation_graph import run_validation_eval_graph
from app.core.database import AsyncSessionLocal
from app.core.validation_settings import normalize_validation_node_settings
from app.models.llm_agent_prompt_version import LLMAgentPromptVersion
from app.models.llm_provider_config import LLMProviderConfig
from app.models.llm_request_log import LLMRequestLog
from app.models.project import Project
from app.models.user import User
from app.models.validation_eval import (
    ValidationEvalCase,
    ValidationEvalCaseResult,
    ValidationEvalDataset,
    ValidationEvalRun,
)
from app.schemas.admin_validation_eval import (
    ValidationEvalCaseCreate,
    ValidationEvalCaseImport,
    ValidationEvalCaseRead,
    ValidationEvalCaseResultRead,
    ValidationEvalCaseUpdate,
    ValidationEvalDatasetDetailRead,
    ValidationEvalDatasetRead,
    ValidationEvalExportArtifact,
    ValidationEvalImportPayload,
    ValidationEvalImportResultRead,
    ValidationEvalRunConfig,
    ValidationEvalRunCreateRead,
    ValidationEvalRunListItemRead,
    ValidationEvalRunPageRead,
    ValidationEvalRunRead,
    ValidationEvalRunStatus,
    ValidationEvalStructuredImport,
    ValidationEvalVariantConfig,
)
from app.services.audit_service import AuditService
from app.services.project_service import ProjectService

VALIDATION_PROMPT_KEYS = {
    VALIDATION_CORE_PROMPT_KEY,
    VALIDATION_CUSTOM_RULES_PROMPT_KEY,
    VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
}


class AdminValidationEvalService:
    @staticmethod
    def _normalize_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _split_multi(value: object) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        separator = "||" if "||" in text else "|"
        if separator not in text and "," in text:
            separator = ","
        return [item.strip() for item in text.split(separator) if item.strip()]

    @staticmethod
    def _parse_json_cell(value: object, default: Any) -> Any:
        text = str(value or "").strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CSV содержит некорректный JSON в одном из полей.",
            ) from exc

    @staticmethod
    def _parse_csv_payload(
        *,
        dataset_name: str | None,
        project_id: str | None,
        content: str | None,
    ) -> ValidationEvalStructuredImport:
        if not dataset_name or not project_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Для CSV-импорта нужны dataset_name и project_id.",
            )
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CSV-контент не должен быть пустым.",
            )

        cases = []
        reader = csv.DictReader(StringIO(content))
        for index, row in enumerate(reader, start=1):
            external_id = (
                AdminValidationEvalService._normalize_text(row.get("case_external_id"))
                or AdminValidationEvalService._normalize_text(row.get("external_id"))
                or f"case-{index}"
            )
            title = AdminValidationEvalService._normalize_text(row.get("title"))
            if not title:
                continue
            cases.append(
                {
                    "external_id": external_id,
                    "title": title,
                    "content": str(row.get("content") or ""),
                    "tags": AdminValidationEvalService._split_multi(row.get("tags")),
                    "attachment_names": AdminValidationEvalService._split_multi(
                        row.get("attachment_names")
                    ),
                    "custom_rules": AdminValidationEvalService._parse_json_cell(
                        row.get("custom_rules_json") or row.get("custom_rules"),
                        [],
                    ),
                    "related_tasks": AdminValidationEvalService._parse_json_cell(
                        row.get("related_tasks_json") or row.get("related_tasks"),
                        [],
                    ),
                    "historical_questions": AdminValidationEvalService._split_multi(
                        row.get("historical_questions")
                    ),
                    "expected_verdict": AdminValidationEvalService._normalize_text(
                        row.get("expected_verdict")
                    )
                    or "approved",
                    "expected_issues": AdminValidationEvalService._parse_json_cell(
                        row.get("expected_issues_json") or row.get("expected_issues"),
                        [],
                    ),
                    "expected_questions": AdminValidationEvalService._split_multi(
                        row.get("expected_questions")
                    ),
                    "expected_context_questions": AdminValidationEvalService._split_multi(
                        row.get("expected_context_questions")
                    ),
                    "metadata": AdminValidationEvalService._parse_json_cell(
                        row.get("metadata_json") or row.get("metadata"),
                        {},
                    ),
                }
            )
        return ValidationEvalStructuredImport.model_validate(
            {
                "dataset_name": dataset_name,
                "project_id": project_id,
                "cases": cases,
            }
        )

    @staticmethod
    def _resolve_import_payload(
        payload: ValidationEvalImportPayload,
    ) -> ValidationEvalStructuredImport:
        if payload.format == "csv":
            return AdminValidationEvalService._parse_csv_payload(
                dataset_name=payload.dataset_name,
                project_id=payload.project_id,
                content=payload.content,
            )
        if payload.payload is not None:
            return payload.payload
        if payload.content:
            try:
                decoded = json.loads(payload.content)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="JSON-импорт не удалось разобрать.",
                ) from exc
            return ValidationEvalStructuredImport.model_validate(decoded)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Для импорта нужен payload или content.",
        )

    @staticmethod
    def _ensure_unique_external_ids(cases: list[Any]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in cases:
            external_id = str(item.external_id).strip()
            if external_id in seen:
                duplicates.add(external_id)
            seen.add(external_id)
        if duplicates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Дублируются external_id кейсов: " + ", ".join(sorted(duplicates)),
            )

    @staticmethod
    async def _project_name(db: AsyncSession, project_id: str) -> str | None:
        project = await db.get(Project, project_id)
        return project.name if project is not None else None

    @staticmethod
    def _case_expected_result(case: ValidationEvalCase) -> dict[str, Any]:
        return {
            "verdict": case.expected_verdict,
            "issues": list(case.expected_issues or []),
            "questions": list(case.expected_questions or []),
            "context_questions": list(case.expected_context_questions or []),
        }

    @staticmethod
    def _case_read(case: ValidationEvalCase) -> ValidationEvalCaseRead:
        return ValidationEvalCaseRead(
            id=case.id,
            external_id=case.external_id,
            title=case.title,
            content=case.content,
            tags=list(case.tags or []),
            attachment_names=list(case.attachment_names or []),
            custom_rules=list(case.custom_rules or []),
            related_tasks=list(case.related_tasks or []),
            historical_questions=list(case.historical_questions or []),
            expected_verdict=cast(Any, case.expected_verdict),
            expected_issues=list(case.expected_issues or []),
            expected_questions=list(case.expected_questions or []),
            expected_context_questions=list(case.expected_context_questions or []),
            metadata=dict(case.case_metadata or {}),
            updated_at=case.updated_at,
        )

    @staticmethod
    async def _dataset_read(
        dataset: ValidationEvalDataset,
        db: AsyncSession,
    ) -> ValidationEvalDatasetRead:
        cases_total = await db.scalar(
            select(func.count())
            .select_from(ValidationEvalCase)
            .where(ValidationEvalCase.dataset_id == dataset.id)
        )
        last_run = (
            await db.execute(
                select(ValidationEvalRun)
                .where(ValidationEvalRun.dataset_id == dataset.id)
                .order_by(ValidationEvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return ValidationEvalDatasetRead(
            id=dataset.id,
            project_id=dataset.project_id,
            project_name=await AdminValidationEvalService._project_name(
                db,
                dataset.project_id,
            ),
            name=dataset.name,
            cases_total=int(cases_total or 0),
            last_run_id=last_run.id if last_run is not None else None,
            last_run_status=cast(ValidationEvalRunStatus, last_run.status)
            if last_run is not None
            else None,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    @staticmethod
    async def _dataset_detail(
        dataset: ValidationEvalDataset,
        db: AsyncSession,
    ) -> ValidationEvalDatasetDetailRead:
        base = await AdminValidationEvalService._dataset_read(dataset, db)
        cases = list(
            (
                await db.execute(
                    select(ValidationEvalCase)
                    .where(ValidationEvalCase.dataset_id == dataset.id)
                    .order_by(ValidationEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        return ValidationEvalDatasetDetailRead(
            **base.model_dump(),
            cases=[AdminValidationEvalService._case_read(case) for case in cases],
        )

    @staticmethod
    async def list_datasets(db: AsyncSession) -> list[ValidationEvalDatasetRead]:
        datasets = list(
            (
                await db.execute(
                    select(ValidationEvalDataset).order_by(
                        ValidationEvalDataset.updated_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            await AdminValidationEvalService._dataset_read(dataset, db)
            for dataset in datasets
        ]

    @staticmethod
    async def get_dataset(
        dataset_id: str,
        db: AsyncSession,
    ) -> ValidationEvalDatasetDetailRead:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-набор не найден.",
            )
        return await AdminValidationEvalService._dataset_detail(dataset, db)

    @staticmethod
    async def _upsert_dataset(
        data: ValidationEvalStructuredImport,
        actor: User,
        db: AsyncSession,
    ) -> ValidationEvalDataset:
        dataset = (
            await db.execute(
                select(ValidationEvalDataset).where(
                    ValidationEvalDataset.project_id == data.project_id,
                    ValidationEvalDataset.name == data.dataset_name,
                )
            )
        ).scalar_one_or_none()
        if dataset is None:
            dataset = ValidationEvalDataset(
                project_id=data.project_id,
                name=data.dataset_name,
                created_by=actor.id,
            )
            db.add(dataset)
            await db.flush()
        else:
            dataset.updated_at = datetime.now(UTC)
        return dataset

    @staticmethod
    def _apply_case_payload(
        case: ValidationEvalCase,
        payload: ValidationEvalCaseCreate | ValidationEvalCaseImport | ValidationEvalCaseUpdate,
        *,
        exclude_unset: bool = True,
    ) -> None:
        updates = payload.model_dump(mode="json", exclude_unset=exclude_unset)
        for field_name, value in updates.items():
            if field_name == "metadata":
                case.case_metadata = dict(value or {})
            elif field_name == "custom_rules":
                case.custom_rules = list(value or [])
            elif field_name == "related_tasks":
                case.related_tasks = list(value or [])
            elif field_name == "expected_issues":
                case.expected_issues = list(value or [])
            else:
                setattr(case, field_name, value)
        case.updated_at = datetime.now(UTC)

    @staticmethod
    async def import_dataset(
        payload: ValidationEvalImportPayload,
        actor: User,
        db: AsyncSession,
    ) -> ValidationEvalImportResultRead:
        data = AdminValidationEvalService._resolve_import_payload(payload)
        AdminValidationEvalService._ensure_unique_external_ids(data.cases)
        await ProjectService.get_project_or_404(data.project_id, db)

        dataset = await AdminValidationEvalService._upsert_dataset(data, actor, db)
        existing_cases = {
            item.external_id: item
            for item in (
                await db.execute(
                    select(ValidationEvalCase).where(
                        ValidationEvalCase.dataset_id == dataset.id
                    )
                )
            )
            .scalars()
            .all()
        }
        imported_cases = 0
        for item in data.cases:
            case = existing_cases.get(item.external_id)
            if case is None:
                case = ValidationEvalCase(
                    dataset_id=dataset.id,
                    external_id=item.external_id,
                    title=item.title,
                    content=item.content,
                    tags=list(item.tags),
                    attachment_names=list(item.attachment_names),
                    custom_rules=[rule.model_dump(mode="json") for rule in item.custom_rules],
                    related_tasks=list(item.related_tasks),
                    historical_questions=list(item.historical_questions),
                    expected_verdict=item.expected_verdict,
                    expected_issues=[
                        issue.model_dump(mode="json", exclude_none=True)
                        for issue in item.expected_issues
                    ],
                    expected_questions=list(item.expected_questions),
                    expected_context_questions=list(item.expected_context_questions),
                    case_metadata=dict(item.metadata),
                )
                db.add(case)
            else:
                AdminValidationEvalService._apply_case_payload(
                    case,
                    item,
                    exclude_unset=False,
                )
            imported_cases += 1

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_dataset_imported",
            entity_type="validation_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
            metadata={"cases": imported_cases},
        )
        await db.commit()
        await db.refresh(dataset)
        return ValidationEvalImportResultRead(
            dataset=await AdminValidationEvalService._dataset_detail(dataset, db),
            imported_cases=imported_cases,
            warnings=[],
        )

    @staticmethod
    async def create_case(
        dataset_id: str,
        payload: ValidationEvalCaseCreate,
        actor: User,
        db: AsyncSession,
    ) -> ValidationEvalCaseRead:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-набор не найден.",
            )
        existing = (
            await db.execute(
                select(ValidationEvalCase).where(
                    ValidationEvalCase.dataset_id == dataset.id,
                    ValidationEvalCase.external_id == payload.external_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Кейс с таким external_id уже существует.",
            )
        case = ValidationEvalCase(
            dataset_id=dataset.id,
            external_id=payload.external_id,
            title=payload.title,
            content=payload.content,
            tags=list(payload.tags),
            attachment_names=list(payload.attachment_names),
            custom_rules=[rule.model_dump(mode="json") for rule in payload.custom_rules],
            related_tasks=list(payload.related_tasks),
            historical_questions=list(payload.historical_questions),
            expected_verdict=payload.expected_verdict,
            expected_issues=[
                issue.model_dump(mode="json", exclude_none=True)
                for issue in payload.expected_issues
            ],
            expected_questions=list(payload.expected_questions),
            expected_context_questions=list(payload.expected_context_questions),
            case_metadata=dict(payload.metadata),
        )
        db.add(case)
        dataset.updated_at = datetime.now(UTC)
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_case_created",
            entity_type="validation_eval_case",
            entity_id=case.id,
            project_id=dataset.project_id,
        )
        await db.commit()
        await db.refresh(case)
        return AdminValidationEvalService._case_read(case)

    @staticmethod
    async def update_case(
        dataset_id: str,
        case_id: str,
        payload: ValidationEvalCaseUpdate,
        actor: User,
        db: AsyncSession,
    ) -> ValidationEvalCaseRead:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        case = await db.get(ValidationEvalCase, case_id)
        if dataset is None or case is None or case.dataset_id != dataset.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-кейс не найден.",
            )
        if payload.external_id and payload.external_id != case.external_id:
            existing = (
                await db.execute(
                    select(ValidationEvalCase).where(
                        ValidationEvalCase.dataset_id == dataset.id,
                        ValidationEvalCase.external_id == payload.external_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Кейс с таким external_id уже существует.",
                )
        AdminValidationEvalService._apply_case_payload(case, payload)
        dataset.updated_at = datetime.now(UTC)
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_case_updated",
            entity_type="validation_eval_case",
            entity_id=case.id,
            project_id=dataset.project_id,
        )
        await db.commit()
        await db.refresh(case)
        return AdminValidationEvalService._case_read(case)

    @staticmethod
    async def delete_case(
        dataset_id: str,
        case_id: str,
        actor: User,
        db: AsyncSession,
    ) -> None:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        case = await db.get(ValidationEvalCase, case_id)
        if dataset is None or case is None or case.dataset_id != dataset.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-кейс не найден.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_case_deleted",
            entity_type="validation_eval_case",
            entity_id=case.id,
            project_id=dataset.project_id,
        )
        await db.delete(case)
        dataset.updated_at = datetime.now(UTC)
        await db.commit()

    @staticmethod
    async def _validate_run_config(config: ValidationEvalRunConfig, db: AsyncSession) -> None:
        for variant in config.variants:
            if variant.provider_config_id:
                provider = await db.get(LLMProviderConfig, variant.provider_config_id)
                if provider is None or not provider.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Провайдер для variant {variant.key} не найден или отключён.",
                    )
            for prompt_key, version_id in variant.prompt_version_ids.items():
                if prompt_key not in VALIDATION_PROMPT_KEYS:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Prompt key {prompt_key} не относится к validation graph.",
                    )
                version = await db.get(LLMAgentPromptVersion, version_id)
                if version is None or version.prompt_key != prompt_key:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Версия промпта {version_id} для {prompt_key} не найдена.",
                    )

    @staticmethod
    async def create_run(
        dataset_id: str,
        config: ValidationEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> ValidationEvalRunCreateRead:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-набор не найден.",
            )
        await AdminValidationEvalService._validate_run_config(config, db)
        run = ValidationEvalRun(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            created_by=actor.id,
            status="queued",
            config=config.model_dump(mode="json"),
        )
        db.add(run)
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_run_created",
            entity_type="validation_eval_run",
            entity_id=run.id,
            project_id=dataset.project_id,
            metadata={"dataset_id": dataset.id},
        )
        await db.commit()
        await db.refresh(run)
        return ValidationEvalRunCreateRead(
            id=run.id,
            dataset_id=run.dataset_id,
            status=cast(ValidationEvalRunStatus, run.status),
            config=ValidationEvalRunConfig.model_validate(run.config),
            created_at=run.created_at,
        )

    @staticmethod
    async def process_run(run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(ValidationEvalRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await db.commit()
            started = perf_counter()
            try:
                await AdminValidationEvalService._process_run_inner(run.id, db)
                run = await db.get(ValidationEvalRun, run_id)
                if run is not None:
                    run.status = "success"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.summary_metrics = await AdminValidationEvalService._summarize_run(
                        run,
                        db,
                    )
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                run = await db.get(ValidationEvalRun, run_id)
                if run is not None:
                    run.status = "error"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.error_message = str(exc)[:1000]
                    await db.commit()

    @staticmethod
    async def _prompt_overrides_for_variant(
        variant: ValidationEvalVariantConfig,
        db: AsyncSession,
    ) -> dict[str, str]:
        overrides: dict[str, str] = {}
        for prompt_key, version_id in variant.prompt_version_ids.items():
            version = await db.get(LLMAgentPromptVersion, version_id)
            if version is not None and version.prompt_key == prompt_key:
                overrides[prompt_key] = version.system_prompt
        return overrides

    @staticmethod
    async def _process_run_inner(run_id: str, db: AsyncSession) -> None:
        run = await db.get(ValidationEvalRun, run_id)
        if run is None:
            return
        config = ValidationEvalRunConfig.model_validate(run.config)
        cases = list(
            (
                await db.execute(
                    select(ValidationEvalCase)
                    .where(ValidationEvalCase.dataset_id == run.dataset_id)
                    .order_by(ValidationEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            for variant in config.variants:
                await AdminValidationEvalService._run_case_variant(
                    run=run,
                    case=case,
                    variant=variant,
                    config=config,
                    db=db,
                )

    @staticmethod
    async def _run_case_variant(
        *,
        run: ValidationEvalRun,
        case: ValidationEvalCase,
        variant: ValidationEvalVariantConfig,
        config: ValidationEvalRunConfig,
        db: AsyncSession,
    ) -> None:
        started = perf_counter()
        expected = AdminValidationEvalService._case_expected_result(case)
        actual: dict[str, Any] = {}
        diffs: dict[str, Any] = {}
        metrics: dict[str, Any] = {}
        judge_payload: dict[str, Any] | None = None
        graph_run_id: str | None = None
        judge_graph_run_id: str | None = None
        error_message: str | None = None
        result_status = "error"
        try:
            validation_state = await run_validation_eval_graph(
                db=db,
                actor_user_id=run.created_by,
                project_id=run.project_id,
                title=case.title,
                content=case.content,
                tags=list(case.tags or []),
                custom_rules=list(case.custom_rules or []),
                related_tasks=list(case.related_tasks or []),
                attachment_names=list(case.attachment_names or []),
                historical_questions=list(case.historical_questions or []),
                validation_node_settings=normalize_validation_node_settings(
                    variant.validation_node_settings
                ),
                provider_config_id=variant.provider_config_id,
                prompt_overrides=await AdminValidationEvalService._prompt_overrides_for_variant(
                    variant,
                    db,
                ),
            )
            graph_run_id = (
                str(validation_state.get("graph_run_id"))
                if validation_state.get("graph_run_id")
                else None
            )
            actual = {
                "verdict": str(validation_state.get("verdict", "approved")),
                "issues": list(validation_state.get("issues", [])),
                "questions": list(validation_state.get("questions", [])),
                "llm_diagnostics": list(validation_state.get("llm_diagnostics", [])),
                "core_issues": list(validation_state.get("core_issues", [])),
                "core_questions": list(validation_state.get("core_questions", [])),
                "custom_rule_issues": list(validation_state.get("custom_rule_issues", [])),
                "context_questions": list(validation_state.get("context_questions", [])),
                "rag_questions": list(validation_state.get("rag_questions", [])),
            }
            metrics, diffs = AdminValidationEvalService._case_metrics(
                expected=expected,
                actual=actual,
            )
            if config.run_question_judge:
                judge_payload = {}
                judge_graph_run_ids: list[str] = []
                for group_key, metric_prefix, expected_questions, actual_questions in (
                    (
                        "final_questions",
                        "question",
                        list(case.expected_questions or []),
                        [str(item) for item in actual.get("questions", [])],
                    ),
                    (
                        "context_questions",
                        "context_question",
                        list(case.expected_context_questions or []),
                        [str(item) for item in actual.get("context_questions", [])],
                    ),
                ):
                    if not expected_questions and not actual_questions:
                        continue
                    judge_state = await run_validation_eval_question_judge_graph(
                        db=db,
                        actor_user_id=run.created_by,
                        project_id=run.project_id,
                        task_title=case.title,
                        task_content=case.content,
                        expected_questions=expected_questions,
                        actual_questions=actual_questions,
                    )
                    group_payload = dict(judge_state.get("judge_payload", {}))
                    group_graph_run_id = (
                        str(judge_state.get("judge_graph_run_id"))
                        if judge_state.get("judge_graph_run_id")
                        else None
                    )
                    if group_graph_run_id:
                        group_payload["judge_graph_run_id"] = group_graph_run_id
                        judge_graph_run_ids.append(group_graph_run_id)
                        judge_graph_run_id = judge_graph_run_id or group_graph_run_id
                    judge_payload[group_key] = group_payload
                    AdminValidationEvalService._merge_judge_metrics(
                        metrics,
                        group_payload,
                        prefix=metric_prefix,
                    )
                if judge_graph_run_ids:
                    metrics["judge_graph_run_ids"] = judge_graph_run_ids
                if not judge_payload:
                    judge_payload = None
            result_status = "passed" if metrics.get("passed") else "failed"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)[:1000]
            metrics = {"passed": False, "error": True}
            diffs = {"error": error_message}

        db.add(
            ValidationEvalCaseResult(
                run_id=run.id,
                case_id=case.id,
                graph_run_id=graph_run_id,
                judge_graph_run_id=judge_graph_run_id,
                variant_key=variant.key,
                variant_label=variant.label,
                status=result_status,
                expected_result=expected,
                actual_result=actual,
                diffs=diffs,
                judge_payload=judge_payload,
                metrics=metrics,
                latency_ms=int((perf_counter() - started) * 1000),
                error_message=error_message,
            )
        )
        await db.commit()

    @staticmethod
    def _issue_identity(issue: dict[str, Any]) -> str:
        code = str(issue.get("code") or "").strip().casefold()
        if code:
            return f"code:{code}"
        return f"message:{AdminValidationEvalService._normalize_match_text(issue.get('message'))}"

    @staticmethod
    def _normalize_match_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").casefold()).strip()

    @staticmethod
    def _message_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
        expected_text = AdminValidationEvalService._normalize_match_text(expected.get("message"))
        actual_text = AdminValidationEvalService._normalize_match_text(actual.get("message"))
        if not expected_text or not actual_text:
            return False
        return expected_text in actual_text or actual_text in expected_text

    @staticmethod
    def _match_issues(
        expected_issues: list[dict[str, Any]],
        actual_issues: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        unmatched_actual = list(actual_issues)
        matched: list[dict[str, Any]] = []
        false_negatives: list[dict[str, Any]] = []
        for expected in expected_issues:
            expected_identity = AdminValidationEvalService._issue_identity(expected)
            match_index: int | None = None
            for index, actual in enumerate(unmatched_actual):
                if expected_identity == AdminValidationEvalService._issue_identity(actual):
                    match_index = index
                    break
                if AdminValidationEvalService._message_matches(expected, actual):
                    match_index = index
                    break
            if match_index is None:
                false_negatives.append(expected)
                continue
            actual = unmatched_actual.pop(match_index)
            matched.append({"expected": expected, "actual": actual})
        return matched, unmatched_actual, false_negatives

    @staticmethod
    def _is_custom_rule_issue(issue: dict[str, Any]) -> bool:
        source = str(issue.get("source") or "").casefold()
        code = str(issue.get("code") or "").casefold()
        return source in {"custom_rule", "custom_rules"} or bool(
            issue.get("rule_title")
        ) or code.startswith("custom_rule")

    @staticmethod
    def _issue_source(issue: dict[str, Any]) -> str:
        source = str(issue.get("source") or "").casefold()
        code = str(issue.get("code") or "").casefold()
        if source in {"context_question", "context_questions"} or code == "context_question":
            return "context"
        if AdminValidationEvalService._is_custom_rule_issue(issue):
            return "custom"
        return "core"

    @staticmethod
    def _source_issue_scores(
        expected_issues: list[dict[str, Any]],
        actual_issues: list[dict[str, Any]],
        source: str,
    ) -> dict[str, Any]:
        expected = [
            issue
            for issue in expected_issues
            if AdminValidationEvalService._issue_source(issue) == source
        ]
        actual = [
            issue
            for issue in actual_issues
            if AdminValidationEvalService._issue_source(issue) == source
        ]
        matches, false_positives, false_negatives = AdminValidationEvalService._match_issues(
            expected,
            actual,
        )
        scores = AdminValidationEvalService._prf(
            len(matches),
            len(false_positives),
            len(false_negatives),
        )
        return {
            "tp": len(matches),
            "fp": len(false_positives),
            "fn": len(false_negatives),
            "precision": scores["precision"],
            "recall": scores["recall"],
            "f1": scores["f1"],
        }

    @staticmethod
    def _match_text_items(
        expected_items: list[str],
        actual_items: list[str],
    ) -> tuple[list[dict[str, str]], list[str], list[str], int]:
        normalized_actual = [
            AdminValidationEvalService._normalize_match_text(item) for item in actual_items
        ]
        duplicate_count = max(0, len(normalized_actual) - len(set(normalized_actual)))
        unmatched_actual = list(actual_items)
        matched: list[dict[str, str]] = []
        false_negatives: list[str] = []
        for expected in expected_items:
            expected_text = AdminValidationEvalService._normalize_match_text(expected)
            match_index: int | None = None
            for index, actual in enumerate(unmatched_actual):
                actual_text = AdminValidationEvalService._normalize_match_text(actual)
                if (
                    expected_text == actual_text
                    or expected_text in actual_text
                    or actual_text in expected_text
                ):
                    match_index = index
                    break
            if match_index is None:
                false_negatives.append(expected)
                continue
            actual = unmatched_actual.pop(match_index)
            matched.append({"expected": expected, "actual": actual})
        return matched, unmatched_actual, false_negatives, duplicate_count

    @staticmethod
    def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
        precision = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
        recall = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @staticmethod
    def _text_item_scores(
        expected_items: list[str],
        actual_items: list[str],
        prefix: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        matches, extra_items, missing_items, duplicate_count = (
            AdminValidationEvalService._match_text_items(expected_items, actual_items)
        )
        scores = AdminValidationEvalService._prf(
            len(matches),
            len(extra_items),
            len(missing_items),
        )
        metrics = {
            f"{prefix}_tp": len(matches),
            f"{prefix}_fp": len(extra_items),
            f"{prefix}_fn": len(missing_items),
            f"{prefix}_precision": scores["precision"],
            f"{prefix}_recall": scores["recall"],
            f"{prefix}_f1": scores["f1"],
            f"{prefix}_duplicates": duplicate_count,
            f"{prefix}_duplicate_rate": round(duplicate_count / len(actual_items), 4)
            if actual_items
            else 0,
        }
        if prefix == "question":
            diffs = {
                "question_matches": matches,
                "extra_questions": extra_items,
                "missing_questions": missing_items,
            }
        elif prefix == "context_question":
            diffs = {
                "context_question_matches": matches,
                "extra_context_questions": extra_items,
                "missing_context_questions": missing_items,
            }
        else:
            diffs = {
                f"{prefix}_matches": matches,
                f"extra_{prefix}s": extra_items,
                f"missing_{prefix}s": missing_items,
            }
        return metrics, diffs

    @staticmethod
    def _case_metrics(
        *,
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        expected_issues = [dict(item) for item in expected.get("issues", [])]
        actual_issues = [dict(item) for item in actual.get("issues", [])]
        issue_matches, false_positives, false_negatives = AdminValidationEvalService._match_issues(
            expected_issues,
            actual_issues,
        )
        issue_scores = AdminValidationEvalService._prf(
            len(issue_matches),
            len(false_positives),
            len(false_negatives),
        )
        severity_total = 0
        severity_hits = 0
        for match in issue_matches:
            expected_severity = match["expected"].get("severity")
            if expected_severity:
                severity_total += 1
                severity_hits += int(expected_severity == match["actual"].get("severity"))

        expected_questions = [str(item) for item in expected.get("questions", [])]
        actual_questions = [str(item) for item in actual.get("questions", [])]
        question_metrics, question_diffs = AdminValidationEvalService._text_item_scores(
            expected_questions,
            actual_questions,
            "question",
        )
        expected_context_questions = [
            str(item) for item in expected.get("context_questions", [])
        ]
        actual_context_questions = [str(item) for item in actual.get("context_questions", [])]
        context_question_metrics, context_question_diffs = (
            AdminValidationEvalService._text_item_scores(
                expected_context_questions,
                actual_context_questions,
                "context_question",
            )
        )
        overall_question_scores = AdminValidationEvalService._prf(
            int(question_metrics["question_tp"])
            + int(context_question_metrics["context_question_tp"]),
            int(question_metrics["question_fp"])
            + int(context_question_metrics["context_question_fp"]),
            int(question_metrics["question_fn"])
            + int(context_question_metrics["context_question_fn"]),
        )
        custom_expected = [
            issue
            for issue in expected_issues
            if AdminValidationEvalService._is_custom_rule_issue(issue)
        ]
        custom_matched = [
            match
            for match in issue_matches
            if AdminValidationEvalService._is_custom_rule_issue(match["expected"])
        ]
        source_scores = {
            source: AdminValidationEvalService._source_issue_scores(
                expected_issues,
                actual_issues,
                source,
            )
            for source in ("core", "custom", "context")
        }
        verdict_match = expected.get("verdict") == actual.get("verdict")
        strict_passed = (
            verdict_match
            and not false_positives
            and not false_negatives
            and not question_diffs["extra_questions"]
            and not question_diffs["missing_questions"]
            and not context_question_diffs["extra_context_questions"]
            and not context_question_diffs["missing_context_questions"]
        )
        diagnostics = list(actual.get("llm_diagnostics", []))
        llm_errors = sum(1 for item in diagnostics if item.get("error_message"))
        json_errors = sum(1 for item in diagnostics if item.get("parse_error"))
        fallback_total = sum(1 for item in diagnostics if item.get("used_fallback"))
        metrics = {
            "passed": strict_passed,
            "verdict_match": verdict_match,
            "expected_verdict": expected.get("verdict"),
            "actual_verdict": actual.get("verdict"),
            "issue_tp": len(issue_matches),
            "issue_fp": len(false_positives),
            "issue_fn": len(false_negatives),
            "issue_precision": issue_scores["precision"],
            "issue_recall": issue_scores["recall"],
            "issue_f1": issue_scores["f1"],
            "severity_total": severity_total,
            "severity_hits": severity_hits,
            "severity_accuracy": round(severity_hits / severity_total, 4)
            if severity_total
            else None,
            "custom_rule_expected": len(custom_expected),
            "custom_rule_matched": len(custom_matched),
            "custom_rule_coverage": round(len(custom_matched) / len(custom_expected), 4)
            if custom_expected
            else None,
            **{
                f"{source}_issue_{metric_key}": metric_value
                for source, scores in source_scores.items()
                for metric_key, metric_value in scores.items()
            },
            **question_metrics,
            **context_question_metrics,
            "overall_question_tp": int(question_metrics["question_tp"])
            + int(context_question_metrics["context_question_tp"]),
            "overall_question_fp": int(question_metrics["question_fp"])
            + int(context_question_metrics["context_question_fp"]),
            "overall_question_fn": int(question_metrics["question_fn"])
            + int(context_question_metrics["context_question_fn"]),
            "overall_question_precision": overall_question_scores["precision"],
            "overall_question_recall": overall_question_scores["recall"],
            "overall_question_f1": overall_question_scores["f1"],
            "overall_question_duplicates": int(question_metrics["question_duplicates"])
            + int(context_question_metrics["context_question_duplicates"]),
            "overall_question_duplicate_rate": round(
                (
                    int(question_metrics["question_duplicates"])
                    + int(context_question_metrics["context_question_duplicates"])
                )
                / (len(actual_questions) + len(actual_context_questions)),
                4,
            )
            if actual_questions or actual_context_questions
            else 0,
            "llm_errors": llm_errors,
            "json_errors": json_errors,
            "fallback_total": fallback_total,
        }
        diffs = {
            "issue_matches": issue_matches,
            "false_positive_issues": false_positives,
            "false_negative_issues": false_negatives,
            **question_diffs,
            **context_question_diffs,
        }
        return metrics, diffs

    @staticmethod
    def _merge_judge_metrics(
        metrics: dict[str, Any],
        judge_payload: dict[str, Any],
        *,
        prefix: str = "question",
    ) -> None:
        for key in ("relevance", "specificity", "actionability", "novelty"):
            value = judge_payload.get(key)
            if isinstance(value, int | float):
                metrics[f"{prefix}_{key}"] = round(float(value), 4)
        metrics[f"{prefix}_judge_ok"] = bool(judge_payload.get("ok"))

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
        return ordered[index]

    @staticmethod
    async def _summarize_run(run: ValidationEvalRun, db: AsyncSession) -> dict[str, Any]:
        results = list(
            (
                await db.execute(
                    select(ValidationEvalCaseResult).where(
                        ValidationEvalCaseResult.run_id == run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        graph_run_ids: list[str] = []
        for item in results:
            graph_run_ids.extend(
                [value for value in (item.graph_run_id, item.judge_graph_run_id) if value]
            )
            extra_judge_ids = (item.metrics or {}).get("judge_graph_run_ids")
            if isinstance(extra_judge_ids, list):
                graph_run_ids.extend(str(value) for value in extra_judge_ids if value)
        graph_run_ids = list(dict.fromkeys(graph_run_ids))
        token_totals = await AdminValidationEvalService._token_totals(graph_run_ids, db)
        by_variant: dict[str, list[ValidationEvalCaseResult]] = {}
        for result in results:
            by_variant.setdefault(result.variant_key, []).append(result)
        variants = {
            variant_key: AdminValidationEvalService._summarize_variant(items, token_totals)
            for variant_key, items in sorted(by_variant.items())
        }
        return {
            "total_results": len(results),
            "variants": variants,
            "ablation": AdminValidationEvalService._ablation_summary(variants),
        }

    @staticmethod
    async def _token_totals(
        graph_run_ids: list[str],
        db: AsyncSession,
    ) -> dict[str, dict[str, Any]]:
        if not graph_run_ids:
            return {}
        logs = list(
            (
                await db.execute(
                    select(LLMRequestLog).where(LLMRequestLog.graph_run_id.in_(graph_run_ids))
                )
            )
            .scalars()
            .all()
        )
        totals: dict[str, dict[str, Any]] = {}
        for log in logs:
            if not log.graph_run_id:
                continue
            item = totals.setdefault(
                log.graph_run_id,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": Decimal("0"),
                },
            )
            item["prompt_tokens"] += int(log.prompt_tokens or 0)
            item["completion_tokens"] += int(log.completion_tokens or 0)
            item["total_tokens"] += int(log.total_tokens or 0)
            if log.estimated_cost_usd is not None:
                item["estimated_cost_usd"] += Decimal(log.estimated_cost_usd)
        return totals

    @staticmethod
    def _summarize_variant(
        results: list[ValidationEvalCaseResult],
        token_totals: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        total = len(results)
        passed = len([item for item in results if item.status == "passed"])
        failed = len([item for item in results if item.status == "failed"])
        errors = len([item for item in results if item.status == "error"])
        latencies = [item.latency_ms for item in results if item.latency_ms is not None]
        issue_tp = sum(int(item.metrics.get("issue_tp") or 0) for item in results)
        issue_fp = sum(int(item.metrics.get("issue_fp") or 0) for item in results)
        issue_fn = sum(int(item.metrics.get("issue_fn") or 0) for item in results)
        question_tp = sum(int(item.metrics.get("question_tp") or 0) for item in results)
        question_fp = sum(int(item.metrics.get("question_fp") or 0) for item in results)
        question_fn = sum(int(item.metrics.get("question_fn") or 0) for item in results)
        context_question_tp = sum(
            int(item.metrics.get("context_question_tp") or 0) for item in results
        )
        context_question_fp = sum(
            int(item.metrics.get("context_question_fp") or 0) for item in results
        )
        context_question_fn = sum(
            int(item.metrics.get("context_question_fn") or 0) for item in results
        )
        overall_question_tp = question_tp + context_question_tp
        overall_question_fp = question_fp + context_question_fp
        overall_question_fn = question_fn + context_question_fn
        severity_total = sum(int(item.metrics.get("severity_total") or 0) for item in results)
        severity_hits = sum(int(item.metrics.get("severity_hits") or 0) for item in results)
        custom_expected = sum(
            int(item.metrics.get("custom_rule_expected") or 0) for item in results
        )
        custom_matched = sum(
            int(item.metrics.get("custom_rule_matched") or 0) for item in results
        )
        confusion: dict[str, dict[str, int]] = {}
        for item in results:
            expected = str(item.metrics.get("expected_verdict") or "unknown")
            actual = str(item.metrics.get("actual_verdict") or "unknown")
            confusion.setdefault(expected, {})
            confusion[expected][actual] = confusion[expected].get(actual, 0) + 1

        token_summary = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": Decimal("0"),
        }
        for item in results:
            result_graph_ids = [
                value for value in (item.graph_run_id, item.judge_graph_run_id) if value
            ]
            extra_judge_ids = (item.metrics or {}).get("judge_graph_run_ids")
            if isinstance(extra_judge_ids, list):
                result_graph_ids.extend(str(value) for value in extra_judge_ids if value)
            for graph_run_id in dict.fromkeys(result_graph_ids):
                if graph_run_id and graph_run_id in token_totals:
                    graph_tokens = token_totals[graph_run_id]
                    token_summary["prompt_tokens"] += int(graph_tokens["prompt_tokens"])
                    token_summary["completion_tokens"] += int(
                        graph_tokens["completion_tokens"]
                    )
                    token_summary["total_tokens"] += int(graph_tokens["total_tokens"])
                    token_summary["estimated_cost_usd"] += Decimal(
                        graph_tokens["estimated_cost_usd"]
                    )

        judge_scores: dict[str, dict[str, list[float]]] = {
            prefix: {key: [] for key in ("relevance", "specificity", "actionability", "novelty")}
            for prefix in ("question", "context_question")
        }
        for item in results:
            for prefix, prefix_scores in judge_scores.items():
                for key in prefix_scores:
                    value = item.metrics.get(f"{prefix}_{key}")
                    if isinstance(value, int | float):
                        prefix_scores[key].append(float(value))

        issue_scores = AdminValidationEvalService._prf(issue_tp, issue_fp, issue_fn)
        question_scores = AdminValidationEvalService._prf(
            question_tp,
            question_fp,
            question_fn,
        )
        context_question_scores = AdminValidationEvalService._prf(
            context_question_tp,
            context_question_fp,
            context_question_fn,
        )
        overall_question_scores = AdminValidationEvalService._prf(
            overall_question_tp,
            overall_question_fp,
            overall_question_fn,
        )
        source_issue_scores = {
            source: AdminValidationEvalService._prf(
                sum(int(item.metrics.get(f"{source}_issue_tp") or 0) for item in results),
                sum(int(item.metrics.get(f"{source}_issue_fp") or 0) for item in results),
                sum(int(item.metrics.get(f"{source}_issue_fn") or 0) for item in results),
            )
            for source in ("core", "custom", "context")
        }
        final_judge = {
            key: round(sum(values) / len(values), 4) if values else None
            for key, values in judge_scores["question"].items()
        }
        context_judge = {
            key: round(sum(values) / len(values), 4) if values else None
            for key, values in judge_scores["context_question"].items()
        }
        overall_judge: dict[str, float | None] = {}
        for key in ("relevance", "specificity", "actionability", "novelty"):
            values = [
                *judge_scores["question"][key],
                *judge_scores["context_question"][key],
            ]
            overall_judge[key] = round(sum(values) / len(values), 4) if values else None
        return {
            "cases_total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total, 4) if total else 0,
            "verdict_accuracy": round(
                sum(bool(item.metrics.get("verdict_match")) for item in results)
                / max(total, 1),
                4,
            ),
            "confusion_matrix": confusion,
            "issue_precision": issue_scores["precision"],
            "issue_recall": issue_scores["recall"],
            "issue_f1": issue_scores["f1"],
            "core_issue_precision": source_issue_scores["core"]["precision"],
            "core_issue_recall": source_issue_scores["core"]["recall"],
            "core_issue_f1": source_issue_scores["core"]["f1"],
            "custom_issue_precision": source_issue_scores["custom"]["precision"],
            "custom_issue_recall": source_issue_scores["custom"]["recall"],
            "custom_issue_f1": source_issue_scores["custom"]["f1"],
            "context_issue_precision": source_issue_scores["context"]["precision"],
            "context_issue_recall": source_issue_scores["context"]["recall"],
            "context_issue_f1": source_issue_scores["context"]["f1"],
            "severity_accuracy": round(severity_hits / severity_total, 4)
            if severity_total
            else None,
            "custom_rule_coverage": round(custom_matched / custom_expected, 4)
            if custom_expected
            else None,
            "question_precision": question_scores["precision"],
            "question_recall": question_scores["recall"],
            "question_f1": question_scores["f1"],
            "context_question_precision": context_question_scores["precision"],
            "context_question_recall": context_question_scores["recall"],
            "context_question_f1": context_question_scores["f1"],
            "overall_question_precision": overall_question_scores["precision"],
            "overall_question_recall": overall_question_scores["recall"],
            "overall_question_f1": overall_question_scores["f1"],
            "question_duplicate_rate": round(
                sum(int(item.metrics.get("question_duplicates") or 0) for item in results)
                / max(sum(len(item.actual_result.get("questions", [])) for item in results), 1),
                4,
            ),
            "context_question_duplicate_rate": round(
                sum(
                    int(item.metrics.get("context_question_duplicates") or 0)
                    for item in results
                )
                / max(
                    sum(len(item.actual_result.get("context_questions", [])) for item in results),
                    1,
                ),
                4,
            ),
            "overall_question_duplicate_rate": round(
                sum(
                    int(item.metrics.get("overall_question_duplicates") or 0)
                    for item in results
                )
                / max(
                    sum(
                        len(item.actual_result.get("questions", []))
                        + len(item.actual_result.get("context_questions", []))
                        for item in results
                    ),
                    1,
                ),
                4,
            ),
            "question_judge": final_judge,
            "context_question_judge": context_judge,
            "overall_question_judge": overall_judge,
            "llm_errors": sum(int(item.metrics.get("llm_errors") or 0) for item in results),
            "json_errors": sum(int(item.metrics.get("json_errors") or 0) for item in results),
            "fallback_total": sum(
                int(item.metrics.get("fallback_total") or 0) for item in results
            ),
            "p50_latency_ms": AdminValidationEvalService._percentile(latencies, 0.5),
            "p95_latency_ms": AdminValidationEvalService._percentile(latencies, 0.95),
            "prompt_tokens": int(token_summary["prompt_tokens"]),
            "completion_tokens": int(token_summary["completion_tokens"]),
            "total_tokens": int(token_summary["total_tokens"]),
            "estimated_cost_usd": float(token_summary["estimated_cost_usd"]),
        }

    @staticmethod
    def _ablation_summary(variants: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        baseline = variants.get("full")
        if baseline is None:
            return []
        rows: list[dict[str, Any]] = []
        for key, metrics in sorted(variants.items()):
            if key == "full":
                continue
            rows.append(
                {
                    "variant_key": key,
                    "baseline_variant": "full",
                    "pass_rate_delta": round(
                        float(metrics.get("pass_rate") or 0)
                        - float(baseline.get("pass_rate") or 0),
                        4,
                    ),
                    "verdict_accuracy_delta": round(
                        float(metrics.get("verdict_accuracy") or 0)
                        - float(baseline.get("verdict_accuracy") or 0),
                        4,
                    ),
                    "issue_f1_delta": round(
                        float(metrics.get("issue_f1") or 0)
                        - float(baseline.get("issue_f1") or 0),
                        4,
                    ),
                    "context_issue_f1_delta": round(
                        float(metrics.get("context_issue_f1") or 0)
                        - float(baseline.get("context_issue_f1") or 0),
                        4,
                    ),
                    "question_f1_delta": round(
                        float(metrics.get("question_f1") or 0)
                        - float(baseline.get("question_f1") or 0),
                        4,
                    ),
                    "context_question_f1_delta": round(
                        float(metrics.get("context_question_f1") or 0)
                        - float(baseline.get("context_question_f1") or 0),
                        4,
                    ),
                    "overall_question_f1_delta": round(
                        float(metrics.get("overall_question_f1") or 0)
                        - float(baseline.get("overall_question_f1") or 0),
                        4,
                    ),
                }
            )
        return rows

    @staticmethod
    async def list_runs(
        dataset_id: str,
        db: AsyncSession,
        *,
        run_status: ValidationEvalRunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ValidationEvalRunPageRead:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-набор не найден.",
            )
        conditions = [ValidationEvalRun.dataset_id == dataset.id]
        if run_status is not None:
            conditions.append(ValidationEvalRun.status == run_status)
        total = await db.scalar(
            select(func.count()).select_from(ValidationEvalRun).where(*conditions)
        )
        runs = list(
            (
                await db.execute(
                    select(ValidationEvalRun)
                    .where(*conditions)
                    .order_by(ValidationEvalRun.created_at.desc())
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return ValidationEvalRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                ValidationEvalRunListItemRead(
                    id=run.id,
                    dataset_id=run.dataset_id,
                    dataset_name=dataset.name,
                    project_id=run.project_id,
                    status=cast(ValidationEvalRunStatus, run.status),
                    config=ValidationEvalRunConfig.model_validate(run.config),
                    summary_metrics=run.summary_metrics,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    latency_ms=run.latency_ms,
                    error_message=run.error_message,
                    created_at=run.created_at,
                )
                for run in runs
            ],
        )

    @staticmethod
    async def get_run(run_id: str, db: AsyncSession) -> ValidationEvalRunRead:
        run = await db.get(ValidationEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-запуск не найден.",
            )
        dataset = await db.get(ValidationEvalDataset, run.dataset_id)
        rows = list(
            (
                await db.execute(
                    select(ValidationEvalCaseResult, ValidationEvalCase)
                    .join(
                        ValidationEvalCase,
                        ValidationEvalCase.id == ValidationEvalCaseResult.case_id,
                    )
                    .where(ValidationEvalCaseResult.run_id == run.id)
                    .order_by(
                        ValidationEvalCase.external_id.asc(),
                        ValidationEvalCaseResult.variant_key.asc(),
                    )
                )
            ).all()
        )
        return ValidationEvalRunRead(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset.name if dataset is not None else None,
            project_id=run.project_id,
            status=cast(ValidationEvalRunStatus, run.status),
            config=ValidationEvalRunConfig.model_validate(run.config),
            summary_metrics=run.summary_metrics,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            created_at=run.created_at,
            case_results=[
                ValidationEvalCaseResultRead(
                    id=result.id,
                    case_id=result.case_id,
                    case_external_id=case.external_id,
                    variant_key=result.variant_key,
                    variant_label=result.variant_label,
                    status=cast(Any, result.status),
                    graph_run_id=result.graph_run_id,
                    judge_graph_run_id=result.judge_graph_run_id,
                    expected_result=dict(result.expected_result or {}),
                    actual_result=dict(result.actual_result or {}),
                    diffs=dict(result.diffs or {}),
                    judge_payload=dict(result.judge_payload or {})
                    if result.judge_payload is not None
                    else None,
                    metrics=dict(result.metrics or {}),
                    latency_ms=result.latency_ms,
                    error_message=result.error_message,
                    created_at=result.created_at,
                )
                for result, case in rows
            ],
        )

    @staticmethod
    def _artifact_payload(run: ValidationEvalRunRead, artifact: str) -> Any:
        if artifact == "case_results":
            return [item.model_dump(mode="json") for item in run.case_results]
        if artifact == "metrics":
            return run.summary_metrics or {}
        if artifact == "confusion_matrix":
            return {
                key: value.get("confusion_matrix", {})
                for key, value in dict((run.summary_metrics or {}).get("variants") or {}).items()
            }
        if artifact == "ablation":
            return (run.summary_metrics or {}).get("ablation", [])
        if artifact == "errors":
            return AdminValidationEvalService._error_rows(run)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Артефакт экспорта неизвестен.",
        )

    @staticmethod
    def _error_rows(run: ValidationEvalRunRead) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in run.case_results:
            for key, error_type in (
                ("false_positive_issues", "false_positive_issue"),
                ("false_negative_issues", "false_negative_issue"),
                ("extra_questions", "extra_question"),
                ("missing_questions", "missing_question"),
                ("extra_context_questions", "extra_context_question"),
                ("missing_context_questions", "missing_context_question"),
            ):
                payload = item.diffs.get(key)
                if isinstance(payload, list):
                    for value in payload:
                        rows.append(
                            {
                                "case_external_id": item.case_external_id,
                                "variant_key": item.variant_key,
                                "error_type": error_type,
                                "payload": value,
                            }
                        )
            if item.error_message:
                rows.append(
                    {
                        "case_external_id": item.case_external_id,
                        "variant_key": item.variant_key,
                        "error_type": "runtime_error",
                        "payload": item.error_message,
                    }
                )
        return rows

    @staticmethod
    async def export_run(
        run_id: str,
        export_format: str,
        artifact: ValidationEvalExportArtifact,
        db: AsyncSession,
    ) -> tuple[str, str, str]:
        run = await AdminValidationEvalService.get_run(run_id, db)
        payload = AdminValidationEvalService._artifact_payload(run, artifact)
        if export_format == "json":
            return (
                f"validation-eval-{artifact}-{run.id}.json",
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        if export_format != "csv":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Формат экспорта неизвестен.",
            )
        return AdminValidationEvalService._export_csv(run, artifact, payload)

    @staticmethod
    def _export_csv(
        run: ValidationEvalRunRead,
        artifact: str,
        payload: Any,
    ) -> tuple[str, str, str]:
        output = StringIO()
        if artifact == "case_results":
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "case_external_id",
                    "variant_key",
                    "status",
                    "expected_verdict",
                    "actual_verdict",
                    "issue_precision",
                    "issue_recall",
                    "issue_f1",
                    "context_issue_f1",
                    "question_precision",
                    "question_recall",
                    "question_f1",
                    "context_question_precision",
                    "context_question_recall",
                    "context_question_f1",
                    "overall_question_precision",
                    "overall_question_recall",
                    "overall_question_f1",
                    "latency_ms",
                    "graph_run_id",
                    "judge_graph_run_id",
                    "error_message",
                ],
            )
            writer.writeheader()
            for item in run.case_results:
                writer.writerow(
                    {
                        "case_external_id": item.case_external_id,
                        "variant_key": item.variant_key,
                        "status": item.status,
                        "expected_verdict": item.metrics.get("expected_verdict"),
                        "actual_verdict": item.metrics.get("actual_verdict"),
                        "issue_precision": item.metrics.get("issue_precision"),
                        "issue_recall": item.metrics.get("issue_recall"),
                        "issue_f1": item.metrics.get("issue_f1"),
                        "context_issue_f1": item.metrics.get("context_issue_f1"),
                        "question_precision": item.metrics.get("question_precision"),
                        "question_recall": item.metrics.get("question_recall"),
                        "question_f1": item.metrics.get("question_f1"),
                        "context_question_precision": item.metrics.get(
                            "context_question_precision"
                        ),
                        "context_question_recall": item.metrics.get("context_question_recall"),
                        "context_question_f1": item.metrics.get("context_question_f1"),
                        "overall_question_precision": item.metrics.get(
                            "overall_question_precision"
                        ),
                        "overall_question_recall": item.metrics.get("overall_question_recall"),
                        "overall_question_f1": item.metrics.get("overall_question_f1"),
                        "latency_ms": item.latency_ms,
                        "graph_run_id": item.graph_run_id,
                        "judge_graph_run_id": item.judge_graph_run_id,
                        "error_message": item.error_message or "",
                    }
                )
        elif artifact == "metrics":
            writer = csv.DictWriter(output, fieldnames=["variant_key", "metric", "value"])
            writer.writeheader()
            variants = dict((run.summary_metrics or {}).get("variants") or {})
            for variant_key, metrics in variants.items():
                for key, value in dict(metrics).items():
                    if isinstance(value, dict | list):
                        value = json.dumps(value, ensure_ascii=False)
                    writer.writerow({"variant_key": variant_key, "metric": key, "value": value})
        elif artifact == "confusion_matrix":
            writer = csv.DictWriter(
                output,
                fieldnames=["variant_key", "expected_verdict", "actual_verdict", "count"],
            )
            writer.writeheader()
            for variant_key, matrix in dict(payload).items():
                for expected, actuals in dict(matrix).items():
                    for actual, count in dict(actuals).items():
                        writer.writerow(
                            {
                                "variant_key": variant_key,
                                "expected_verdict": expected,
                                "actual_verdict": actual,
                                "count": count,
                            }
                        )
        elif artifact == "ablation":
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "variant_key",
                    "baseline_variant",
                    "pass_rate_delta",
                    "verdict_accuracy_delta",
                    "issue_f1_delta",
                    "context_issue_f1_delta",
                    "question_f1_delta",
                    "context_question_f1_delta",
                    "overall_question_f1_delta",
                ],
            )
            writer.writeheader()
            writer.writerows(payload)
        elif artifact == "errors":
            writer = csv.DictWriter(
                output,
                fieldnames=["case_external_id", "variant_key", "error_type", "payload"],
            )
            writer.writeheader()
            for row in payload:
                writer.writerow(
                    {
                        **row,
                        "payload": json.dumps(row["payload"], ensure_ascii=False)
                        if isinstance(row.get("payload"), dict | list)
                        else row.get("payload"),
                    }
                )
        return (
            f"validation-eval-{artifact}-{run.id}.csv",
            "text/csv; charset=utf-8",
            output.getvalue(),
        )

    @staticmethod
    async def delete_run(run_id: str, actor: User, db: AsyncSession) -> None:
        run = await db.get(ValidationEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-запуск не найден.",
            )
        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить Validation eval-запуск, который ещё выполняется.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_run_deleted",
            entity_type="validation_eval_run",
            entity_id=run.id,
            project_id=run.project_id,
            metadata={"dataset_id": run.dataset_id, "status": run.status},
        )
        await db.delete(run)
        await db.commit()

    @staticmethod
    async def delete_dataset(dataset_id: str, actor: User, db: AsyncSession) -> None:
        dataset = await db.get(ValidationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Validation eval-набор не найден.",
            )
        active_runs = await db.scalar(
            select(func.count())
            .select_from(ValidationEvalRun)
            .where(
                ValidationEvalRun.dataset_id == dataset.id,
                ValidationEvalRun.status.in_(["queued", "running"]),
            )
        )
        if active_runs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить набор, пока есть активные Validation eval-запуски.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.validation_eval_dataset_deleted",
            entity_type="validation_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
        )
        await db.delete(dataset)
        await db.commit()
