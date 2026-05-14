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

from app.agents.chat_agents.registry import parse_requested_agent
from app.agents.chat_routing_eval_graph import run_chat_routing_eval_graph
from app.core.database import AsyncSessionLocal
from app.models.llm_request_log import LLMRequestLog
from app.models.message import Message
from app.models.orchestrator_eval import (
    OrchestratorEvalCase,
    OrchestratorEvalCaseResult,
    OrchestratorEvalDataset,
    OrchestratorEvalRun,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.admin_orchestrator_eval import (
    OrchestratorEvalCaseImport,
    OrchestratorEvalCaseRead,
    OrchestratorEvalCaseResultRead,
    OrchestratorEvalDatasetDetailRead,
    OrchestratorEvalDatasetRead,
    OrchestratorEvalExpectedRoute,
    OrchestratorEvalImportPayload,
    OrchestratorEvalImportResultRead,
    OrchestratorEvalInput,
    OrchestratorEvalPlaygroundResultRead,
    OrchestratorEvalPlaygroundRunPayload,
    OrchestratorEvalRunConfig,
    OrchestratorEvalRunCreateRead,
    OrchestratorEvalRunListItemRead,
    OrchestratorEvalRunPageRead,
    OrchestratorEvalRunRead,
    OrchestratorEvalRunStatus,
    OrchestratorEvalStructuredImport,
)
from app.services.audit_service import AuditService


class AdminOrchestratorEvalService:
    @staticmethod
    def _normalize_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _parse_bool(value: object) -> bool | None:
        text = str(value or "").strip().casefold()
        if text in {"true", "yes", "1", "да"}:
            return True
        if text in {"false", "no", "0", "нет"}:
            return False
        return None

    @staticmethod
    def _expected_route_dict(route: OrchestratorEvalExpectedRoute | None) -> dict[str, Any]:
        if route is None:
            return {}
        return route.model_dump(mode="json", exclude_unset=True)

    @staticmethod
    def _input_from_case(case: OrchestratorEvalCase) -> OrchestratorEvalInput:
        return OrchestratorEvalInput(
            project_id=case.project_id,
            task_id=case.task_id,
            task_title=case.task_title,
            task_status=case.task_status,
            task_content=case.task_content,
            validation_result=case.validation_result,
            message_content=case.message_content,
            requested_agent=case.requested_agent,
        )

    @staticmethod
    def _parse_csv_payload(
        *,
        dataset_name: str | None,
        project_id: str | None,
        content: str | None,
    ) -> OrchestratorEvalStructuredImport:
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

        reader = csv.DictReader(StringIO(content))
        cases: list[OrchestratorEvalCaseImport] = []
        for index, row in enumerate(reader, start=1):
            external_id = (
                AdminOrchestratorEvalService._normalize_text(row.get("case_external_id"))
                or f"case-{index}"
            )
            message_content = AdminOrchestratorEvalService._normalize_text(
                row.get("message_content")
            )
            if not message_content:
                continue

            expected_payload: dict[str, Any] = {}
            expected_ai = AdminOrchestratorEvalService._parse_bool(
                row.get("expected_ai_response_required")
            )
            if expected_ai is not None:
                expected_payload["ai_response_required"] = expected_ai
            for csv_key, route_key in (
                ("expected_target_agent_key", "target_agent_key"),
                ("expected_message_type", "message_type"),
                ("expected_routing_mode", "routing_mode"),
                ("expected_reason_contains", "reason_contains"),
            ):
                text = AdminOrchestratorEvalService._normalize_text(row.get(csv_key))
                if text:
                    expected_payload[route_key] = text

            task_status = (
                AdminOrchestratorEvalService._normalize_text(row.get("task_status"))
                or "draft"
            )
            cases.append(
                OrchestratorEvalCaseImport(
                    external_id=external_id,
                    input=OrchestratorEvalInput(
                        project_id=project_id,
                        task_id=AdminOrchestratorEvalService._normalize_text(
                            row.get("task_id")
                        )
                        or None,
                        task_title=AdminOrchestratorEvalService._normalize_text(
                            row.get("task_title")
                        )
                        or external_id,
                        task_status=task_status,
                        task_content=str(row.get("task_content") or ""),
                        validation_result=None,
                        message_content=message_content,
                        requested_agent=AdminOrchestratorEvalService._normalize_text(
                            row.get("requested_agent")
                        )
                        or None,
                    ),
                    expected_route=OrchestratorEvalExpectedRoute.model_validate(
                        expected_payload
                    ),
                )
            )
        return OrchestratorEvalStructuredImport(
            dataset_name=dataset_name,
            project_id=project_id,
            cases=cases,
        )

    @staticmethod
    def _resolve_import_payload(
        payload: OrchestratorEvalImportPayload,
    ) -> OrchestratorEvalStructuredImport:
        if payload.format == "csv":
            return AdminOrchestratorEvalService._parse_csv_payload(
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
            return OrchestratorEvalStructuredImport.model_validate(decoded)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Для импорта нужен payload или content.",
        )

    @staticmethod
    async def _project_name(db: AsyncSession, project_id: str) -> str | None:
        project = await db.get(Project, project_id)
        return project.name if project is not None else None

    @staticmethod
    async def _dataset_read(
        dataset: OrchestratorEvalDataset,
        db: AsyncSession,
    ) -> OrchestratorEvalDatasetRead:
        cases_total = await db.scalar(
            select(func.count())
            .select_from(OrchestratorEvalCase)
            .where(OrchestratorEvalCase.dataset_id == dataset.id)
        )
        last_run = (
            await db.execute(
                select(OrchestratorEvalRun)
                .where(OrchestratorEvalRun.dataset_id == dataset.id)
                .order_by(OrchestratorEvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return OrchestratorEvalDatasetRead(
            id=dataset.id,
            project_id=dataset.project_id,
            project_name=await AdminOrchestratorEvalService._project_name(
                db, dataset.project_id
            ),
            name=dataset.name,
            cases_total=int(cases_total or 0),
            last_run_id=last_run.id if last_run is not None else None,
            last_run_status=cast(OrchestratorEvalRunStatus, last_run.status)
            if last_run is not None
            else None,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    @staticmethod
    async def _dataset_detail(
        dataset: OrchestratorEvalDataset,
        db: AsyncSession,
    ) -> OrchestratorEvalDatasetDetailRead:
        base = await AdminOrchestratorEvalService._dataset_read(dataset, db)
        cases = list(
            (
                await db.execute(
                    select(OrchestratorEvalCase)
                    .where(OrchestratorEvalCase.dataset_id == dataset.id)
                    .order_by(OrchestratorEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        return OrchestratorEvalDatasetDetailRead(
            **base.model_dump(),
            cases=[
                OrchestratorEvalCaseRead(
                    id=item.id,
                    external_id=item.external_id,
                    input=AdminOrchestratorEvalService._input_from_case(item),
                    expected_route=dict(item.expected_route or {}),
                    updated_at=item.updated_at,
                )
                for item in cases
            ],
        )

    @staticmethod
    async def list_datasets(db: AsyncSession) -> list[OrchestratorEvalDatasetRead]:
        datasets = list(
            (
                await db.execute(
                    select(OrchestratorEvalDataset).order_by(
                        OrchestratorEvalDataset.updated_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            await AdminOrchestratorEvalService._dataset_read(dataset, db)
            for dataset in datasets
        ]

    @staticmethod
    async def get_dataset(
        dataset_id: str,
        db: AsyncSession,
    ) -> OrchestratorEvalDatasetDetailRead:
        dataset = await db.get(OrchestratorEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orchestrator eval-набор не найден.",
            )
        return await AdminOrchestratorEvalService._dataset_detail(dataset, db)

    @staticmethod
    async def import_dataset(
        payload: OrchestratorEvalImportPayload,
        actor: User,
        db: AsyncSession,
    ) -> OrchestratorEvalImportResultRead:
        data = AdminOrchestratorEvalService._resolve_import_payload(payload)
        project = await db.get(Project, data.project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проект для Orchestrator Eval не найден.",
            )

        dataset = (
            await db.execute(
                select(OrchestratorEvalDataset).where(
                    OrchestratorEvalDataset.project_id == data.project_id,
                    OrchestratorEvalDataset.name == data.dataset_name,
                )
            )
        ).scalar_one_or_none()
        if dataset is None:
            dataset = OrchestratorEvalDataset(
                project_id=data.project_id,
                name=data.dataset_name,
                created_by=actor.id,
            )
            db.add(dataset)
            await db.flush()

        imported_cases = 0
        warnings: list[str] = []
        for item in data.cases:
            if item.input.project_id != data.project_id:
                warnings.append(
                    f"{item.external_id}: project_id заменен на project_id набора."
                )
            case_input = item.input.model_copy(update={"project_id": data.project_id})
            existing = (
                await db.execute(
                    select(OrchestratorEvalCase).where(
                        OrchestratorEvalCase.dataset_id == dataset.id,
                        OrchestratorEvalCase.external_id == item.external_id,
                    )
                )
            ).scalar_one_or_none()
            expected_route = AdminOrchestratorEvalService._expected_route_dict(
                item.expected_route
            )
            if existing is None:
                existing = OrchestratorEvalCase(
                    dataset_id=dataset.id,
                    external_id=item.external_id,
                    project_id=data.project_id,
                    task_id=case_input.task_id,
                    task_title=case_input.task_title,
                    task_status=case_input.task_status,
                    task_content=case_input.task_content,
                    validation_result=case_input.validation_result,
                    message_content=case_input.message_content,
                    requested_agent=case_input.requested_agent,
                    expected_route=expected_route,
                )
                db.add(existing)
            else:
                existing.project_id = data.project_id
                existing.task_id = case_input.task_id
                existing.task_title = case_input.task_title
                existing.task_status = case_input.task_status
                existing.task_content = case_input.task_content
                existing.validation_result = case_input.validation_result
                existing.message_content = case_input.message_content
                existing.requested_agent = case_input.requested_agent
                existing.expected_route = expected_route
            imported_cases += 1

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.orchestrator_eval_dataset_imported",
            entity_type="orchestrator_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
            metadata={"cases": imported_cases},
        )
        await db.commit()
        await db.refresh(dataset)
        return OrchestratorEvalImportResultRead(
            dataset=await AdminOrchestratorEvalService._dataset_detail(dataset, db),
            imported_cases=imported_cases,
            warnings=warnings,
        )

    @staticmethod
    def _prepare_input(input_data: OrchestratorEvalInput) -> tuple[str | None, str, str]:
        requested_agent = input_data.requested_agent
        routed_content = input_data.message_content.strip()
        raw_content = routed_content
        if requested_agent is None:
            requested_agent, routed_content = parse_requested_agent(raw_content)
        return requested_agent, routed_content, raw_content

    @staticmethod
    async def _execute_input(
        *,
        input_data: OrchestratorEvalInput,
        expected_route: dict[str, Any],
        config: OrchestratorEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> OrchestratorEvalPlaygroundResultRead:
        requested_agent, routed_content, raw_content = (
            AdminOrchestratorEvalService._prepare_input(input_data)
        )
        started = perf_counter()
        try:
            state = await run_chat_routing_eval_graph(
                db=db,
                task_id=input_data.task_id,
                project_id=input_data.project_id,
                actor_user_id=actor.id,
                task_title=input_data.task_title,
                task_status=input_data.task_status,
                task_content=input_data.task_content,
                message_content=routed_content,
                validation_result=input_data.validation_result,
                requested_agent=requested_agent,
                raw_message_content=raw_content,
            )
            latency_ms = int((perf_counter() - started) * 1000)
            actual_route = dict(state.get("actual_route", {}))
            graph_run_id = state.get("graph_run_id")
            metrics = AdminOrchestratorEvalService._route_metrics(
                expected_route=expected_route,
                actual_route=actual_route,
                compare_reason=config.compare_reason,
            )
            result_status = "passed" if metrics["passed"] else "failed"
            return OrchestratorEvalPlaygroundResultRead(
                status=cast(Any, result_status),
                input=input_data,
                expected_route=expected_route,
                actual_route=actual_route,
                metrics=metrics,
                graph_run_id=str(graph_run_id) if graph_run_id else None,
                latency_ms=latency_ms,
                error_message=None,
            )
        except Exception as exc:  # noqa: BLE001
            return OrchestratorEvalPlaygroundResultRead(
                status="error",
                input=input_data,
                expected_route=expected_route,
                actual_route={},
                metrics={"passed": False, "error": True, "field_matches": {}},
                graph_run_id=None,
                latency_ms=int((perf_counter() - started) * 1000),
                error_message=str(exc)[:1000],
            )

    @staticmethod
    def _route_metrics(
        *,
        expected_route: dict[str, Any],
        actual_route: dict[str, Any],
        compare_reason: bool,
    ) -> dict[str, Any]:
        field_matches: dict[str, bool] = {}
        for field in (
            "ai_response_required",
            "target_agent_key",
            "message_type",
            "routing_mode",
        ):
            if field in expected_route:
                field_matches[field] = expected_route.get(field) == actual_route.get(field)
        if compare_reason and expected_route.get("reason_contains"):
            expected_text = str(expected_route["reason_contains"]).casefold()
            actual_reason = str(actual_route.get("routing_reason") or "").casefold()
            field_matches["reason_contains"] = expected_text in actual_reason
        passed = all(field_matches.values()) if field_matches else True
        return {
            "passed": passed,
            "evaluated_fields": len(field_matches),
            "field_matches": field_matches,
        }

    @staticmethod
    async def run_playground(
        payload: OrchestratorEvalPlaygroundRunPayload,
        actor: User,
        db: AsyncSession,
    ) -> OrchestratorEvalPlaygroundResultRead:
        return await AdminOrchestratorEvalService._execute_input(
            input_data=payload.input,
            expected_route=AdminOrchestratorEvalService._expected_route_dict(
                payload.expected_route
            ),
            config=payload.config,
            actor=actor,
            db=db,
        )

    @staticmethod
    async def create_run(
        dataset_id: str,
        config: OrchestratorEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> OrchestratorEvalRunCreateRead:
        dataset = await db.get(OrchestratorEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orchestrator eval-набор не найден.",
            )
        run = OrchestratorEvalRun(
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
            event_type="admin.orchestrator_eval_run_created",
            entity_type="orchestrator_eval_run",
            entity_id=run.id,
            project_id=dataset.project_id,
            metadata={"dataset_id": dataset.id},
        )
        await db.commit()
        await db.refresh(run)
        return OrchestratorEvalRunCreateRead(
            id=run.id,
            dataset_id=run.dataset_id,
            status=cast(OrchestratorEvalRunStatus, run.status),
            config=OrchestratorEvalRunConfig.model_validate(run.config),
            created_at=run.created_at,
        )

    @staticmethod
    async def process_run(run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(OrchestratorEvalRun, run_id)
            if run is None:
                return
            actor = await db.get(User, run.created_by)
            if actor is None:
                return
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await db.commit()
            started = perf_counter()
            try:
                await AdminOrchestratorEvalService._process_run_inner(run, actor, db)
                run = await db.get(OrchestratorEvalRun, run_id)
                if run is not None:
                    run.status = "success"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.summary_metrics = await AdminOrchestratorEvalService._summarize_run(
                        run, db
                    )
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                run = await db.get(OrchestratorEvalRun, run_id)
                if run is not None:
                    run.status = "error"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.error_message = str(exc)[:1000]
                    await db.commit()

    @staticmethod
    async def _process_run_inner(
        run: OrchestratorEvalRun,
        actor: User,
        db: AsyncSession,
    ) -> None:
        config = OrchestratorEvalRunConfig.model_validate(run.config)
        cases = list(
            (
                await db.execute(
                    select(OrchestratorEvalCase)
                    .where(OrchestratorEvalCase.dataset_id == run.dataset_id)
                    .order_by(OrchestratorEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            result = await AdminOrchestratorEvalService._execute_input(
                input_data=AdminOrchestratorEvalService._input_from_case(case),
                expected_route=dict(case.expected_route or {}),
                config=config,
                actor=actor,
                db=db,
            )
            db.add(
                OrchestratorEvalCaseResult(
                    run_id=run.id,
                    case_id=case.id,
                    graph_run_id=result.graph_run_id,
                    status=result.status,
                    expected_route=result.expected_route,
                    actual_route=result.actual_route,
                    metrics=result.metrics,
                    latency_ms=result.latency_ms,
                    error_message=result.error_message,
                )
            )
            await db.commit()

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
        return ordered[index]

    @staticmethod
    async def _summarize_run(run: OrchestratorEvalRun, db: AsyncSession) -> dict[str, Any]:
        results = list(
            (
                await db.execute(
                    select(OrchestratorEvalCaseResult).where(
                        OrchestratorEvalCaseResult.run_id == run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        total = len(results)
        passed = len([item for item in results if item.status == "passed"])
        failed = len([item for item in results if item.status == "failed"])
        errors = len([item for item in results if item.status == "error"])
        latencies = [item.latency_ms for item in results if item.latency_ms is not None]
        field_totals: dict[str, int] = {}
        field_hits: dict[str, int] = {}
        for item in results:
            matches = dict((item.metrics or {}).get("field_matches") or {})
            for field, matched in matches.items():
                field_totals[field] = field_totals.get(field, 0) + 1
                if matched:
                    field_hits[field] = field_hits.get(field, 0) + 1

        graph_run_ids = [item.graph_run_id for item in results if item.graph_run_id]
        prompt_tokens = completion_tokens = total_tokens = 0
        estimated_cost = Decimal("0")
        if graph_run_ids:
            logs = list(
                (
                    await db.execute(
                        select(LLMRequestLog).where(
                            LLMRequestLog.graph_run_id.in_(graph_run_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for log in logs:
                prompt_tokens += int(log.prompt_tokens or 0)
                completion_tokens += int(log.completion_tokens or 0)
                total_tokens += int(log.total_tokens or 0)
                if log.estimated_cost_usd is not None:
                    estimated_cost += Decimal(log.estimated_cost_usd)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total, 4) if total else 0,
            "field_accuracy": {
                field: round(field_hits.get(field, 0) / count, 4)
                for field, count in sorted(field_totals.items())
                if count
            },
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2)
            if latencies
            else None,
            "p95_latency_ms": AdminOrchestratorEvalService._percentile(latencies, 0.95),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": str(estimated_cost) if estimated_cost else None,
        }

    @staticmethod
    async def list_runs(
        dataset_id: str,
        db: AsyncSession,
        *,
        run_status: OrchestratorEvalRunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OrchestratorEvalRunPageRead:
        dataset = await db.get(OrchestratorEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orchestrator eval-набор не найден.",
            )
        conditions = [OrchestratorEvalRun.dataset_id == dataset.id]
        if run_status is not None:
            conditions.append(OrchestratorEvalRun.status == run_status)
        total = await db.scalar(
            select(func.count()).select_from(OrchestratorEvalRun).where(*conditions)
        )
        runs = list(
            (
                await db.execute(
                    select(OrchestratorEvalRun)
                    .where(*conditions)
                    .order_by(OrchestratorEvalRun.created_at.desc())
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return OrchestratorEvalRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                OrchestratorEvalRunListItemRead(
                    id=run.id,
                    dataset_id=run.dataset_id,
                    dataset_name=dataset.name,
                    project_id=run.project_id,
                    status=cast(OrchestratorEvalRunStatus, run.status),
                    config=OrchestratorEvalRunConfig.model_validate(run.config),
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
    async def get_run(run_id: str, db: AsyncSession) -> OrchestratorEvalRunRead:
        run = await db.get(OrchestratorEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orchestrator eval-запуск не найден.",
            )
        dataset = await db.get(OrchestratorEvalDataset, run.dataset_id)
        rows = list(
            (
                await db.execute(
                    select(OrchestratorEvalCaseResult, OrchestratorEvalCase)
                    .join(
                        OrchestratorEvalCase,
                        OrchestratorEvalCase.id == OrchestratorEvalCaseResult.case_id,
                    )
                    .where(OrchestratorEvalCaseResult.run_id == run.id)
                    .order_by(OrchestratorEvalCase.external_id.asc())
                )
            ).all()
        )
        return OrchestratorEvalRunRead(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset.name if dataset is not None else None,
            project_id=run.project_id,
            status=cast(OrchestratorEvalRunStatus, run.status),
            config=OrchestratorEvalRunConfig.model_validate(run.config),
            summary_metrics=run.summary_metrics,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            created_at=run.created_at,
            case_results=[
                OrchestratorEvalCaseResultRead(
                    id=result.id,
                    case_id=result.case_id,
                    case_external_id=case.external_id,
                    input=AdminOrchestratorEvalService._input_from_case(case),
                    expected_route=dict(result.expected_route or {}),
                    actual_route=dict(result.actual_route or {}),
                    status=cast(Any, result.status),
                    metrics=dict(result.metrics or {}),
                    graph_run_id=result.graph_run_id,
                    latency_ms=result.latency_ms,
                    error_message=result.error_message,
                    created_at=result.created_at,
                )
                for result, case in rows
            ],
        )

    @staticmethod
    async def export_run(run_id: str, export_format: str, db: AsyncSession) -> tuple[str, str, str]:
        run = await AdminOrchestratorEvalService.get_run(run_id, db)
        if export_format == "json":
            return (
                f"orchestrator-eval-{run.id}.json",
                "application/json; charset=utf-8",
                json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2),
            )
        if export_format != "csv":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Формат экспорта неизвестен.",
            )
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "case_external_id",
                "status",
                "message_content",
                "expected_ai_response_required",
                "actual_ai_response_required",
                "expected_target_agent_key",
                "actual_target_agent_key",
                "expected_message_type",
                "actual_message_type",
                "expected_routing_mode",
                "actual_routing_mode",
                "routing_reason",
                "latency_ms",
                "graph_run_id",
                "error_message",
            ],
        )
        writer.writeheader()
        for item in run.case_results:
            writer.writerow(
                {
                    "case_external_id": item.case_external_id,
                    "status": item.status,
                    "message_content": item.input.message_content,
                    "expected_ai_response_required": item.expected_route.get(
                        "ai_response_required"
                    ),
                    "actual_ai_response_required": item.actual_route.get(
                        "ai_response_required"
                    ),
                    "expected_target_agent_key": item.expected_route.get("target_agent_key"),
                    "actual_target_agent_key": item.actual_route.get("target_agent_key"),
                    "expected_message_type": item.expected_route.get("message_type"),
                    "actual_message_type": item.actual_route.get("message_type"),
                    "expected_routing_mode": item.expected_route.get("routing_mode"),
                    "actual_routing_mode": item.actual_route.get("routing_mode"),
                    "routing_reason": item.actual_route.get("routing_reason"),
                    "latency_ms": item.latency_ms,
                    "graph_run_id": item.graph_run_id,
                    "error_message": item.error_message or "",
                }
            )
        return f"orchestrator-eval-{run.id}.csv", "text/csv; charset=utf-8", output.getvalue()

    @staticmethod
    async def delete_run(run_id: str, actor: User, db: AsyncSession) -> None:
        run = await db.get(OrchestratorEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Orchestrator eval-запуск не найден.",
            )
        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить Orchestrator eval-запуск, который ещё выполняется.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.orchestrator_eval_run_deleted",
            entity_type="orchestrator_eval_run",
            entity_id=run.id,
            project_id=run.project_id,
            metadata={"dataset_id": run.dataset_id, "status": run.status},
        )
        await db.delete(run)
        await db.commit()

    @staticmethod
    async def count_business_artifacts(db: AsyncSession) -> dict[str, int]:
        from app.models.change_proposal import ChangeProposal
        from app.models.validation_question import ValidationQuestion

        return {
            "messages": int(await db.scalar(select(func.count()).select_from(Message)) or 0),
            "proposals": int(
                await db.scalar(select(func.count()).select_from(ChangeProposal)) or 0
            ),
            "validation_questions": int(
                await db.scalar(select(func.count()).select_from(ValidationQuestion)) or 0
            ),
        }
