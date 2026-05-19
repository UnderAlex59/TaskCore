from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import UTC, datetime
from io import StringIO
from time import perf_counter
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.validation_graph import run_validation_graph
from app.core.database import AsyncSessionLocal
from app.models.adaptation_eval import (
    AdaptationEvalCase,
    AdaptationEvalCaseResult,
    AdaptationEvalDataset,
    AdaptationEvalRun,
)
from app.models.message import Message
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.validation_question import ValidationQuestion
from app.schemas.admin_adaptation_eval import (
    AdaptationEvalCaseRead,
    AdaptationEvalCaseResultRead,
    AdaptationEvalDatasetDetailRead,
    AdaptationEvalDatasetRead,
    AdaptationEvalExportArtifact,
    AdaptationEvalImportPayload,
    AdaptationEvalImportResultRead,
    AdaptationEvalRunConfig,
    AdaptationEvalRunCreateRead,
    AdaptationEvalRunListItemRead,
    AdaptationEvalRunPageRead,
    AdaptationEvalRunRead,
    AdaptationEvalRunStatus,
)
from app.schemas.message import MessageCreate
from app.services.audit_service import AuditService
from app.services.chat_service import ChatService
from app.services.project_service import ProjectService
from app.services.qdrant_service import QdrantService
from app.services.task_service import TaskService


class AdminAdaptationEvalService:
    @staticmethod
    def _normalize_match_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").casefold()).strip()

    @staticmethod
    def _match_tokens(value: object) -> set[str]:
        return set(re.findall(r"[A-Za-zА-Яа-яЁё0-9_]{4,}", str(value or "").casefold()))

    @staticmethod
    def _text_matches(expected: object, actual: object) -> bool:
        expected_text = AdminAdaptationEvalService._normalize_match_text(expected)
        actual_text = AdminAdaptationEvalService._normalize_match_text(actual)
        if not expected_text or not actual_text:
            return False
        if (
            expected_text == actual_text
            or expected_text in actual_text
            or actual_text in expected_text
        ):
            return True
        expected_tokens = AdminAdaptationEvalService._match_tokens(expected_text)
        actual_tokens = AdminAdaptationEvalService._match_tokens(actual_text)
        if not expected_tokens or not actual_tokens:
            return False
        overlap = len(expected_tokens & actual_tokens) / len(expected_tokens | actual_tokens)
        return overlap >= 0.55

    @staticmethod
    def _match_text_items(
        expected_items: list[str],
        actual_items: list[str],
    ) -> tuple[list[dict[str, str]], list[str], list[str], int]:
        normalized_actual = [
            AdminAdaptationEvalService._normalize_match_text(item) for item in actual_items
        ]
        duplicate_count = max(0, len(normalized_actual) - len(set(normalized_actual)))
        unmatched_actual = list(actual_items)
        matches: list[dict[str, str]] = []
        missing: list[str] = []
        for expected in expected_items:
            match_index: int | None = None
            for index, actual in enumerate(unmatched_actual):
                if AdminAdaptationEvalService._text_matches(expected, actual):
                    match_index = index
                    break
            if match_index is None:
                missing.append(expected)
                continue
            actual = unmatched_actual.pop(match_index)
            matches.append({"expected": expected, "actual": actual})
        return matches, unmatched_actual, missing, duplicate_count

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
    def _text_scores(
        *,
        expected_items: list[str],
        actual_items: list[str],
        prefix: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        matches, extra, missing, duplicates = AdminAdaptationEvalService._match_text_items(
            expected_items,
            actual_items,
        )
        scores = AdminAdaptationEvalService._prf(len(matches), len(extra), len(missing))
        return (
            {
                f"{prefix}_tp": len(matches),
                f"{prefix}_fp": len(extra),
                f"{prefix}_fn": len(missing),
                f"{prefix}_precision": scores["precision"],
                f"{prefix}_recall": scores["recall"],
                f"{prefix}_f1": scores["f1"],
                f"{prefix}_duplicates": duplicates,
                f"{prefix}_duplicate_rate": round(duplicates / len(actual_items), 4)
                if actual_items
                else 0,
            },
            {
                f"{prefix}_matches": matches,
                f"extra_{prefix}s": extra,
                f"missing_{prefix}s": missing,
            },
        )

    @staticmethod
    def _issue_message(issue: dict[str, Any]) -> str:
        return str(issue.get("message") or "").strip()

    @staticmethod
    def _issue_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
        expected_code = str(expected.get("code") or "").strip().casefold()
        actual_code = str(actual.get("code") or "").strip().casefold()
        if expected_code and actual_code and expected_code == actual_code:
            return True
        return AdminAdaptationEvalService._text_matches(
            AdminAdaptationEvalService._issue_message(expected),
            AdminAdaptationEvalService._issue_message(actual),
        )

    @staticmethod
    def _context_issues(validation_result: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in list(validation_result.get("issues", []))
            if str(dict(item).get("source") or "").casefold() == "context_questions"
            or str(dict(item).get("code") or "").casefold() == "context_question"
        ]

    @staticmethod
    def _issue_scores(
        *,
        expected_issues: list[dict[str, Any]],
        actual_issues: list[dict[str, Any]],
        prefix: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        unmatched_actual = list(actual_issues)
        matches: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for expected in expected_issues:
            match_index: int | None = None
            for index, actual in enumerate(unmatched_actual):
                if AdminAdaptationEvalService._issue_matches(expected, actual):
                    match_index = index
                    break
            if match_index is None:
                missing.append(expected)
                continue
            actual = unmatched_actual.pop(match_index)
            matches.append({"expected": expected, "actual": actual})
        scores = AdminAdaptationEvalService._prf(
            len(matches),
            len(unmatched_actual),
            len(missing),
        )
        return (
            {
                f"{prefix}_tp": len(matches),
                f"{prefix}_fp": len(unmatched_actual),
                f"{prefix}_fn": len(missing),
                f"{prefix}_precision": scores["precision"],
                f"{prefix}_recall": scores["recall"],
                f"{prefix}_f1": scores["f1"],
            },
            {
                f"{prefix}_matches": matches,
                f"extra_{prefix}s": unmatched_actual,
                f"missing_{prefix}s": missing,
            },
        )

    @staticmethod
    def _mrr(expected_items: list[str], actual_items: list[str]) -> float:
        if not expected_items:
            return 1.0 if not actual_items else 0.0
        for rank, actual in enumerate(actual_items, start=1):
            if any(
                AdminAdaptationEvalService._text_matches(expected, actual)
                for expected in expected_items
            ):
                return round(1 / rank, 4)
        return 0.0

    @staticmethod
    def _case_expected_result(case: AdaptationEvalCase) -> dict[str, Any]:
        return {
            "captured_questions": list(case.expected_captured_questions or []),
            "retrieved_questions": list(case.expected_retrieved_questions or []),
            "context_questions": list(case.expected_context_questions or []),
            "verdict": case.expected_verdict,
            "context_issues": list(case.expected_context_issues or []),
        }

    @staticmethod
    def _uuid_or_none(value: object) -> str | None:
        try:
            return str(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _case_metrics(
        *,
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        captured_questions = [str(item) for item in actual.get("captured_questions", [])]
        capture_metrics, capture_diffs = AdminAdaptationEvalService._text_scores(
            expected_items=[str(item) for item in expected.get("captured_questions", [])],
            actual_items=captured_questions,
            prefix="capture",
        )
        retrieval_metrics, retrieval_diffs = AdminAdaptationEvalService._text_scores(
            expected_items=[str(item) for item in expected.get("retrieved_questions", [])],
            actual_items=[str(item) for item in actual.get("retrieved_questions", [])],
            prefix="retrieval",
        )
        retrieval_metrics["retrieval_mrr"] = AdminAdaptationEvalService._mrr(
            [str(item) for item in expected.get("retrieved_questions", [])],
            [str(item) for item in actual.get("retrieved_questions", [])],
        )

        context_validation = dict(
            actual.get("context_validation") or actual.get("full_validation") or {}
        )
        context_question_metrics, context_question_diffs = (
            AdminAdaptationEvalService._text_scores(
                expected_items=[str(item) for item in expected.get("context_questions", [])],
                actual_items=[
                    str(item) for item in context_validation.get("context_questions", [])
                ],
                prefix="context_question",
            )
        )
        context_issue_metrics, context_issue_diffs = (
            AdminAdaptationEvalService._issue_scores(
                expected_issues=[dict(item) for item in expected.get("context_issues", [])],
                actual_issues=AdminAdaptationEvalService._context_issues(
                    context_validation
                ),
                prefix="context_issue",
            )
        )
        verdict_match = expected.get("verdict") == context_validation.get("verdict")
        duplicate_total = int(capture_metrics["capture_duplicates"]) + int(
            context_question_metrics["context_question_duplicates"]
        )
        duplicate_denominator = len(captured_questions) + len(
            list(context_validation.get("context_questions", []))
        )
        metrics = {
            "passed": bool(
                verdict_match
                and capture_metrics["capture_f1"] == 1
                and retrieval_metrics["retrieval_f1"] == 1
                and context_question_metrics["context_question_f1"] == 1
                and context_issue_metrics["context_issue_f1"] == 1
            ),
            "verdict_match": verdict_match,
            "expected_verdict": expected.get("verdict"),
            "actual_verdict": context_validation.get("verdict"),
            **capture_metrics,
            "capture_rate": capture_metrics["capture_recall"],
            **retrieval_metrics,
            "retrieval_precision_at_k": retrieval_metrics["retrieval_precision"],
            "retrieval_recall_at_k": retrieval_metrics["retrieval_recall"],
            **context_question_metrics,
            **context_issue_metrics,
            "overall_question_duplicate_rate": round(
                duplicate_total / duplicate_denominator,
                4,
            )
            if duplicate_denominator
            else 0,
        }
        diffs = {
            **capture_diffs,
            **retrieval_diffs,
            **context_question_diffs,
            **context_issue_diffs,
        }
        return metrics, diffs

    @staticmethod
    async def _project_name(db: AsyncSession, project_id: str) -> str | None:
        project = await db.get(Project, project_id)
        return project.name if project is not None else None

    @staticmethod
    async def _dataset_read(
        dataset: AdaptationEvalDataset,
        db: AsyncSession,
    ) -> AdaptationEvalDatasetRead:
        cases_total = await db.scalar(
            select(func.count())
            .select_from(AdaptationEvalCase)
            .where(AdaptationEvalCase.dataset_id == dataset.id)
        )
        last_run = (
            await db.execute(
                select(AdaptationEvalRun)
                .where(AdaptationEvalRun.dataset_id == dataset.id)
                .order_by(AdaptationEvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return AdaptationEvalDatasetRead(
            id=dataset.id,
            project_id=dataset.project_id,
            project_name=await AdminAdaptationEvalService._project_name(db, dataset.project_id),
            name=dataset.name,
            cases_total=int(cases_total or 0),
            last_run_id=last_run.id if last_run is not None else None,
            last_run_status=cast(AdaptationEvalRunStatus, last_run.status)
            if last_run is not None
            else None,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    @staticmethod
    def _case_read(case: AdaptationEvalCase) -> AdaptationEvalCaseRead:
        return AdaptationEvalCaseRead(
            id=case.id,
            external_id=case.external_id,
            scenario_type=case.scenario_type,
            historical_tasks=list(case.historical_tasks or []),
            probe_task=dict(case.probe_task or {}),
            expected_captured_questions=list(case.expected_captured_questions or []),
            expected_retrieved_questions=list(case.expected_retrieved_questions or []),
            expected_context_questions=list(case.expected_context_questions or []),
            expected_verdict=cast(Any, case.expected_verdict),
            expected_context_issues=list(case.expected_context_issues or []),
            metadata=dict(case.case_metadata or {}),
            updated_at=case.updated_at,
        )

    @staticmethod
    async def _dataset_detail(
        dataset: AdaptationEvalDataset,
        db: AsyncSession,
    ) -> AdaptationEvalDatasetDetailRead:
        base = await AdminAdaptationEvalService._dataset_read(dataset, db)
        cases = list(
            (
                await db.execute(
                    select(AdaptationEvalCase)
                    .where(AdaptationEvalCase.dataset_id == dataset.id)
                    .order_by(AdaptationEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        return AdaptationEvalDatasetDetailRead(
            **base.model_dump(),
            cases=[AdminAdaptationEvalService._case_read(case) for case in cases],
        )

    @staticmethod
    async def list_datasets(db: AsyncSession) -> list[AdaptationEvalDatasetRead]:
        datasets = list(
            (
                await db.execute(
                    select(AdaptationEvalDataset).order_by(
                        AdaptationEvalDataset.updated_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            await AdminAdaptationEvalService._dataset_read(dataset, db)
            for dataset in datasets
        ]

    @staticmethod
    async def get_dataset(
        dataset_id: str,
        db: AsyncSession,
    ) -> AdaptationEvalDatasetDetailRead:
        dataset = await db.get(AdaptationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-набор не найден.",
            )
        return await AdminAdaptationEvalService._dataset_detail(dataset, db)

    @staticmethod
    def import_template(project_id: str | None = None) -> dict[str, Any]:
        return {
            "dataset_name": "Adaptation eval set",
            "project_id": project_id or "project-id",
            "cases": [
                {
                    "external_id": "adapt-auth-roles-positive",
                    "scenario_type": "positive",
                    "historical_tasks": [
                        {
                            "title": "Авторизация по email",
                            "content": "Нужно описать вход пользователя по email и паролю.",
                            "tags": ["auth"],
                            "chat_messages": [
                                "Какие роли пользователей должны поддерживаться?"
                            ],
                        }
                    ],
                    "probe_task": {
                        "title": "Вход в личный кабинет",
                        "content": "Нужно реализовать вход по email и паролю.",
                        "tags": ["auth"],
                        "custom_rules": [],
                        "related_tasks": [],
                        "attachment_names": [],
                    },
                    "expected_captured_questions": [
                        "Какие роли пользователей должны поддерживаться?"
                    ],
                    "expected_retrieved_questions": [
                        "Какие роли пользователей должны поддерживаться?"
                    ],
                    "expected_context_questions": [
                        "Какие роли пользователей должны поддерживаться?"
                    ],
                    "expected_verdict": "needs_rework",
                    "expected_context_issues": [
                        {
                            "code": "context_question",
                            "severity": "medium",
                            "message": "Какие роли пользователей должны поддерживаться?",
                            "source": "context_questions",
                        }
                    ],
                    "metadata": {"scenario": "chat_to_qdrant_to_validation"},
                }
            ],
        }

    @staticmethod
    async def import_dataset(
        payload: AdaptationEvalImportPayload,
        actor: User,
        db: AsyncSession,
    ) -> AdaptationEvalImportResultRead:
        await ProjectService.get_project_or_404(payload.project_id, db)
        dataset = (
            await db.execute(
                select(AdaptationEvalDataset).where(
                    AdaptationEvalDataset.project_id == payload.project_id,
                    AdaptationEvalDataset.name == payload.dataset_name,
                )
            )
        ).scalar_one_or_none()
        if dataset is None:
            dataset = AdaptationEvalDataset(
                project_id=payload.project_id,
                name=payload.dataset_name,
                created_by=actor.id,
            )
            db.add(dataset)
            await db.flush()
        else:
            dataset.updated_at = datetime.now(UTC)

        existing_cases = {
            item.external_id: item
            for item in (
                await db.execute(
                    select(AdaptationEvalCase).where(
                        AdaptationEvalCase.dataset_id == dataset.id
                    )
                )
            )
            .scalars()
            .all()
        }
        imported_cases = 0
        for item in payload.cases:
            item_data = item.model_dump(mode="json")
            case = existing_cases.get(item.external_id)
            if case is None:
                case = AdaptationEvalCase(
                    dataset_id=dataset.id,
                    external_id=item.external_id,
                    scenario_type=item.scenario_type,
                    historical_tasks=list(item_data["historical_tasks"]),
                    probe_task=dict(item_data["probe_task"]),
                    expected_captured_questions=list(item.expected_captured_questions),
                    expected_retrieved_questions=list(item.expected_retrieved_questions),
                    expected_context_questions=list(item.expected_context_questions),
                    expected_verdict=item.expected_verdict,
                    expected_context_issues=list(item_data["expected_context_issues"]),
                    case_metadata=dict(item.metadata),
                )
                db.add(case)
            else:
                case.scenario_type = item.scenario_type
                case.historical_tasks = list(item_data["historical_tasks"])
                case.probe_task = dict(item_data["probe_task"])
                case.expected_captured_questions = list(item.expected_captured_questions)
                case.expected_retrieved_questions = list(item.expected_retrieved_questions)
                case.expected_context_questions = list(item.expected_context_questions)
                case.expected_verdict = item.expected_verdict
                case.expected_context_issues = list(item_data["expected_context_issues"])
                case.case_metadata = dict(item.metadata)
                case.updated_at = datetime.now(UTC)
            imported_cases += 1

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.adaptation_eval_dataset_imported",
            entity_type="adaptation_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
            metadata={"cases": imported_cases},
        )
        await db.commit()
        return AdaptationEvalImportResultRead(
            dataset=await AdminAdaptationEvalService.get_dataset(dataset.id, db),
            imported_cases=imported_cases,
            warnings=[],
        )

    @staticmethod
    async def create_run(
        dataset_id: str,
        config: AdaptationEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> AdaptationEvalRunCreateRead:
        dataset = await db.get(AdaptationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-набор не найден.",
            )
        run = AdaptationEvalRun(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            created_by=actor.id,
            status="queued",
            config=config.model_dump(mode="json"),
        )
        db.add(run)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.adaptation_eval_run_created",
            entity_type="adaptation_eval_run",
            entity_id=run.id,
            project_id=dataset.project_id,
            metadata={"dataset_id": dataset.id},
        )
        await db.commit()
        await db.refresh(run)
        return AdaptationEvalRunCreateRead(
            id=run.id,
            dataset_id=run.dataset_id,
            status=cast(AdaptationEvalRunStatus, run.status),
            config=AdaptationEvalRunConfig.model_validate(run.config),
            created_at=run.created_at,
        )

    @staticmethod
    async def _create_synthetic_task(
        *,
        project_id: str,
        payload: dict[str, Any],
        actor: User,
        db: AsyncSession,
    ) -> Task:
        task = Task(
            project_id=project_id,
            title=str(payload.get("title") or "Synthetic adaptation eval task"),
            content=str(payload.get("content") or ""),
            tags=[str(tag) for tag in list(payload.get("tags") or []) if str(tag).strip()],
            created_by=actor.id,
            analyst_id=actor.id,
        )
        db.add(task)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.adaptation_eval_synthetic_task_created",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
            metadata={"title": task.title},
        )
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def _process_chat_messages(
        *,
        task: Task,
        chat_messages: list[str],
        actor: User,
        db: AsyncSession,
    ) -> None:
        for message in chat_messages:
            stripped = str(message).strip()
            if not stripped:
                continue
            forced_content = (
                stripped if stripped.casefold().startswith("@qa ") else f"@qa {stripped}"
            )
            _, pending = await ChatService.send_message(
                task.id,
                MessageCreate(content=forced_content),
                actor,
                db,
            )
            await ChatService.process_pending_response(pending)

    @staticmethod
    async def _captured_questions(
        task_ids: list[str],
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        rows = list(
            (
                await db.execute(
                    select(ValidationQuestion, Task)
                    .join(Task, Task.id == ValidationQuestion.task_id)
                    .where(ValidationQuestion.task_id.in_(task_ids))
                    .where(ValidationQuestion.source == "chat")
                    .order_by(Task.title.asc(), ValidationQuestion.sort_order.asc())
                )
            ).all()
        )
        return [
            {
                "question_id": question.id,
                "task_id": task.id,
                "task_title": task.title,
                "question_text": question.question_text,
                "validation_verdict": question.validation_verdict,
            }
            for question, task in rows
        ]

    @staticmethod
    async def _agent_message_refs(task_ids: list[str], db: AsyncSession) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        rows = list(
            (
                await db.execute(
                    select(Message)
                    .where(Message.task_id.in_(task_ids))
                    .where(Message.author_id.is_(None))
                    .order_by(Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "message_id": row.id,
                "task_id": row.task_id,
                "agent_name": row.agent_name,
                "source_ref": dict(row.source_ref or {}),
            }
            for row in rows
        ]

    @staticmethod
    async def _probe_retrieval(
        *,
        project_id: str,
        probe_task: dict[str, Any],
        limit: int,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        hits = await QdrantService.probe_project_questions_with_scores(
            project_id=project_id,
            query_text=f"{probe_task.get('title', '')}\n{probe_task.get('content', '')}",
            tags=[str(tag) for tag in list(probe_task.get("tags") or [])],
            limit=limit,
        )
        source_task_ids = [
            task_id
            for item in hits
            if (
                task_id := AdminAdaptationEvalService._uuid_or_none(
                    dict(getattr(item.get("document"), "metadata", {}) or {}).get("task_id")
                )
            )
        ]
        source_task_titles: dict[str, str] = {}
        if source_task_ids:
            rows = (
                await db.execute(
                    select(Task.id, Task.title).where(Task.id.in_(source_task_ids))
                )
            ).all()
            source_task_titles = {str(task_id): str(title) for task_id, title in rows}

        results: list[dict[str, Any]] = []
        for item in hits:
            document = item.get("document")
            metadata = getattr(document, "metadata", {}) if document is not None else {}
            source_task_id = str(dict(metadata or {}).get("task_id") or "")
            results.append(
                {
                    "rank": int(item.get("rank") or len(results) + 1),
                    "score": float(item.get("score") or 0),
                    "question_text": str(getattr(document, "page_content", "")),
                    "metadata": dict(metadata or {}),
                    "source_task": {
                        "id": source_task_id,
                        "title": source_task_titles.get(source_task_id),
                    }
                    if source_task_id
                    else None,
                }
            )
        return results

    @staticmethod
    async def _run_validation_variant(
        *,
        db: AsyncSession,
        actor: User,
        run: AdaptationEvalRun,
        probe_task_id: str,
        probe_task: dict[str, Any],
    ) -> dict[str, Any]:
        validation_node_settings = {
            "core_rules": False,
            "custom_rules": False,
            "context_questions": True,
        }
        state = await run_validation_graph(
            db=db,
            actor_user_id=actor.id,
            task_id=probe_task_id,
            project_id=run.project_id,
            title=str(probe_task.get("title") or ""),
            content=str(probe_task.get("content") or ""),
            tags=[str(tag) for tag in list(probe_task.get("tags") or [])],
            custom_rules=[dict(item) for item in list(probe_task.get("custom_rules") or [])],
            related_tasks=[dict(item) for item in list(probe_task.get("related_tasks") or [])],
            attachment_names=[
                str(item) for item in list(probe_task.get("attachment_names") or [])
            ],
            validation_node_settings=validation_node_settings,
        )
        return {
            "verdict": str(state.get("verdict", "approved")),
            "issues": list(state.get("issues", [])),
            "questions": list(state.get("questions", [])),
            "context_questions": list(state.get("context_questions", [])),
            "rag_questions": list(state.get("rag_questions", [])),
            "llm_diagnostics": list(state.get("llm_diagnostics", [])),
            "graph_run_id": state.get("graph_run_id"),
            "validation_node_settings": validation_node_settings,
        }

    @staticmethod
    async def _cleanup_tasks(
        *,
        task_ids: list[str],
        actor: User,
        db: AsyncSession,
    ) -> list[str]:
        errors: list[str] = []
        for task_id in task_ids:
            task = await db.get(Task, task_id)
            if task is None:
                continue
            try:
                await TaskService.delete_task(task.project_id, task.id, actor, db)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{task_id}: {str(exc)[:300]}")
        return errors

    @staticmethod
    async def _run_case(
        *,
        run: AdaptationEvalRun,
        case: AdaptationEvalCase,
        config: AdaptationEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> None:
        started = perf_counter()
        expected = AdminAdaptationEvalService._case_expected_result(case)
        actual: dict[str, Any] = {}
        metrics: dict[str, Any] = {"passed": False}
        diffs: dict[str, Any] = {}
        error_message: str | None = None
        result_status = "error"
        synthetic_task_ids: list[str] = []
        core_graph_run_id: str | None = None
        full_graph_run_id: str | None = None
        try:
            historical_task_ids: list[str] = []
            for historical_task in list(case.historical_tasks or []):
                task = await AdminAdaptationEvalService._create_synthetic_task(
                    project_id=run.project_id,
                    payload=dict(historical_task),
                    actor=actor,
                    db=db,
                )
                synthetic_task_ids.append(task.id)
                historical_task_ids.append(task.id)
                await AdminAdaptationEvalService._process_chat_messages(
                    task=task,
                    chat_messages=[
                        str(item)
                        for item in list(historical_task.get("chat_messages") or [])
                    ],
                    actor=actor,
                    db=db,
                )

            captured_rows = await AdminAdaptationEvalService._captured_questions(
                historical_task_ids,
                db,
            )
            agent_refs = await AdminAdaptationEvalService._agent_message_refs(
                historical_task_ids,
                db,
            )
            probe_task = await AdminAdaptationEvalService._create_synthetic_task(
                project_id=run.project_id,
                payload=dict(case.probe_task or {}),
                actor=actor,
                db=db,
            )
            synthetic_task_ids.append(probe_task.id)
            retrieval_rows = await AdminAdaptationEvalService._probe_retrieval(
                project_id=run.project_id,
                probe_task=dict(case.probe_task or {}),
                limit=config.retrieval_limit,
                db=db,
            )
            context_validation = await AdminAdaptationEvalService._run_validation_variant(
                db=db,
                actor=actor,
                run=run,
                probe_task_id=probe_task.id,
                probe_task=dict(case.probe_task or {}),
            )
            full_graph_run_id = (
                str(context_validation.get("graph_run_id"))
                if context_validation.get("graph_run_id")
                else None
            )
            actual = {
                "captured_questions": [
                    str(item["question_text"]) for item in captured_rows
                ],
                "captured_question_rows": captured_rows,
                "agent_message_refs": agent_refs,
                "retrieved_questions": [
                    str(item["question_text"]) for item in retrieval_rows
                ],
                "retrieval_results": retrieval_rows,
                "context_validation": context_validation,
            }
            metrics, diffs = AdminAdaptationEvalService._case_metrics(
                expected=expected,
                actual=actual,
            )
            result_status = "passed" if metrics.get("passed") else "failed"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)[:1000]
            diffs = {"error": error_message}
            metrics = {"passed": False, "error": True}
        finally:
            if config.cleanup_synthetic_tasks:
                cleanup_errors = await AdminAdaptationEvalService._cleanup_tasks(
                    task_ids=synthetic_task_ids,
                    actor=actor,
                    db=db,
                )
                if cleanup_errors:
                    actual["cleanup_errors"] = cleanup_errors

        db.add(
            AdaptationEvalCaseResult(
                run_id=run.id,
                case_id=case.id,
                core_graph_run_id=core_graph_run_id,
                full_graph_run_id=full_graph_run_id,
                status=result_status,
                synthetic_task_ids=synthetic_task_ids,
                expected_result=expected,
                actual_result=actual,
                diffs=diffs,
                metrics=metrics,
                latency_ms=int((perf_counter() - started) * 1000),
                error_message=error_message,
            )
        )
        await db.commit()

    @staticmethod
    async def _process_run_inner(run: AdaptationEvalRun, db: AsyncSession) -> None:
        config = AdaptationEvalRunConfig.model_validate(run.config)
        actor = await db.get(User, run.created_by)
        if actor is None:
            raise RuntimeError("Adaptation eval actor not found.")
        cases = list(
            (
                await db.execute(
                    select(AdaptationEvalCase)
                    .where(AdaptationEvalCase.dataset_id == run.dataset_id)
                    .order_by(AdaptationEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            await AdminAdaptationEvalService._run_case(
                run=run,
                case=case,
                config=config,
                actor=actor,
                db=db,
            )

    @staticmethod
    def _gate(
        *,
        key: str,
        label: str,
        value: float,
        threshold: float,
        passed: bool,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "value": round(value, 4),
            "threshold": threshold,
            "passed": passed,
        }

    @staticmethod
    def _summarize_results(
        results: list[AdaptationEvalCaseResult],
        config: AdaptationEvalRunConfig,
    ) -> dict[str, Any]:
        total = len(results)
        passed = len([item for item in results if item.status == "passed"])
        failed = len([item for item in results if item.status == "failed"])
        errors = len([item for item in results if item.status == "error"])

        def summed(metric: str) -> int:
            return sum(int(item.metrics.get(metric) or 0) for item in results)

        capture_scores = AdminAdaptationEvalService._prf(
            summed("capture_tp"),
            summed("capture_fp"),
            summed("capture_fn"),
        )
        retrieval_scores = AdminAdaptationEvalService._prf(
            summed("retrieval_tp"),
            summed("retrieval_fp"),
            summed("retrieval_fn"),
        )
        context_question_scores = AdminAdaptationEvalService._prf(
            summed("context_question_tp"),
            summed("context_question_fp"),
            summed("context_question_fn"),
        )
        context_issue_scores = AdminAdaptationEvalService._prf(
            summed("context_issue_tp"),
            summed("context_issue_fp"),
            summed("context_issue_fn"),
        )
        actual_question_total = sum(
            len(item.actual_result.get("captured_questions", []))
            + len(
                dict(
                    item.actual_result.get("context_validation")
                    or item.actual_result.get("full_validation")
                    or {}
                ).get(
                    "context_questions",
                    [],
                )
            )
            for item in results
        )
        duplicate_total = summed("capture_duplicates") + summed("context_question_duplicates")
        duplicate_rate = round(duplicate_total / max(actual_question_total, 1), 4)
        mrr_values = [
            float(item.metrics.get("retrieval_mrr") or 0)
            for item in results
            if "retrieval_mrr" in item.metrics
        ]
        gates_config = config.quality_gates
        gates = [
            AdminAdaptationEvalService._gate(
                key="capture_recall",
                label="Capture recall",
                value=capture_scores["recall"],
                threshold=gates_config.capture_recall_min,
                passed=capture_scores["recall"] >= gates_config.capture_recall_min,
            ),
            AdminAdaptationEvalService._gate(
                key="retrieval_recall_at_k",
                label="Retrieval recall@k",
                value=retrieval_scores["recall"],
                threshold=gates_config.retrieval_recall_at_k_min,
                passed=retrieval_scores["recall"]
                >= gates_config.retrieval_recall_at_k_min,
            ),
            AdminAdaptationEvalService._gate(
                key="context_question_f1",
                label="Context question F1",
                value=context_question_scores["f1"],
                threshold=gates_config.context_question_f1_min,
                passed=context_question_scores["f1"]
                >= gates_config.context_question_f1_min,
            ),
            AdminAdaptationEvalService._gate(
                key="context_issue_f1",
                label="Context issue F1",
                value=context_issue_scores["f1"],
                threshold=gates_config.context_issue_f1_min,
                passed=context_issue_scores["f1"] >= gates_config.context_issue_f1_min,
            ),
            AdminAdaptationEvalService._gate(
                key="overall_question_duplicate_rate",
                label="Duplicate rate",
                value=duplicate_rate,
                threshold=gates_config.duplicate_rate_max,
                passed=duplicate_rate <= gates_config.duplicate_rate_max,
            ),
        ]
        return {
            "cases_total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total, 4) if total else 0,
            "capture_precision": capture_scores["precision"],
            "capture_recall": capture_scores["recall"],
            "capture_f1": capture_scores["f1"],
            "capture_rate": capture_scores["recall"],
            "retrieval_precision_at_k": retrieval_scores["precision"],
            "retrieval_recall_at_k": retrieval_scores["recall"],
            "retrieval_f1": retrieval_scores["f1"],
            "retrieval_mrr": round(sum(mrr_values) / len(mrr_values), 4)
            if mrr_values
            else 0,
            "context_question_precision": context_question_scores["precision"],
            "context_question_recall": context_question_scores["recall"],
            "context_question_f1": context_question_scores["f1"],
            "context_issue_precision": context_issue_scores["precision"],
            "context_issue_recall": context_issue_scores["recall"],
            "context_issue_f1": context_issue_scores["f1"],
            "overall_question_duplicate_rate": duplicate_rate,
            "quality_gates": gates,
            "gate_status": "passed" if all(gate["passed"] for gate in gates) else "failed",
        }

    @staticmethod
    async def _summarize_run(run: AdaptationEvalRun, db: AsyncSession) -> dict[str, Any]:
        results = list(
            (
                await db.execute(
                    select(AdaptationEvalCaseResult).where(
                        AdaptationEvalCaseResult.run_id == run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return AdminAdaptationEvalService._summarize_results(
            results,
            AdaptationEvalRunConfig.model_validate(run.config),
        )

    @staticmethod
    async def process_run(run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            started = perf_counter()
            run = await db.get(AdaptationEvalRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await db.commit()
            try:
                await AdminAdaptationEvalService._process_run_inner(run, db)
                run = await db.get(AdaptationEvalRun, run_id)
                if run is not None:
                    run.summary_metrics = await AdminAdaptationEvalService._summarize_run(run, db)
                    run.status = "success"
                    run.error_message = None
            except Exception as exc:  # noqa: BLE001
                run = await db.get(AdaptationEvalRun, run_id)
                if run is not None:
                    run.status = "error"
                    run.error_message = str(exc)[:1000]
            if run is not None:
                run.finished_at = datetime.now(UTC)
                run.latency_ms = int((perf_counter() - started) * 1000)
                await db.commit()

    @staticmethod
    async def list_runs(
        dataset_id: str,
        db: AsyncSession,
        *,
        run_status: AdaptationEvalRunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AdaptationEvalRunPageRead:
        dataset = await db.get(AdaptationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-набор не найден.",
            )
        conditions = [AdaptationEvalRun.dataset_id == dataset.id]
        if run_status is not None:
            conditions.append(AdaptationEvalRun.status == run_status)
        total = await db.scalar(
            select(func.count()).select_from(AdaptationEvalRun).where(*conditions)
        )
        runs = list(
            (
                await db.execute(
                    select(AdaptationEvalRun)
                    .where(*conditions)
                    .order_by(AdaptationEvalRun.created_at.desc())
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return AdaptationEvalRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                AdaptationEvalRunListItemRead(
                    id=run.id,
                    dataset_id=run.dataset_id,
                    dataset_name=dataset.name,
                    project_id=run.project_id,
                    status=cast(AdaptationEvalRunStatus, run.status),
                    config=AdaptationEvalRunConfig.model_validate(run.config),
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
    async def get_run(run_id: str, db: AsyncSession) -> AdaptationEvalRunRead:
        run = await db.get(AdaptationEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-запуск не найден.",
            )
        dataset = await db.get(AdaptationEvalDataset, run.dataset_id)
        rows = list(
            (
                await db.execute(
                    select(AdaptationEvalCaseResult, AdaptationEvalCase)
                    .join(
                        AdaptationEvalCase,
                        AdaptationEvalCase.id == AdaptationEvalCaseResult.case_id,
                    )
                    .where(AdaptationEvalCaseResult.run_id == run.id)
                    .order_by(AdaptationEvalCase.external_id.asc())
                )
            ).all()
        )
        return AdaptationEvalRunRead(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset.name if dataset is not None else None,
            project_id=run.project_id,
            status=cast(AdaptationEvalRunStatus, run.status),
            config=AdaptationEvalRunConfig.model_validate(run.config),
            summary_metrics=run.summary_metrics,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            created_at=run.created_at,
            case_results=[
                AdaptationEvalCaseResultRead(
                    id=result.id,
                    case_id=result.case_id,
                    case_external_id=case.external_id,
                    scenario_type=case.scenario_type,
                    status=cast(Any, result.status),
                    core_graph_run_id=result.core_graph_run_id,
                    full_graph_run_id=result.full_graph_run_id,
                    synthetic_task_ids=list(result.synthetic_task_ids or []),
                    expected_result=dict(result.expected_result or {}),
                    actual_result=dict(result.actual_result or {}),
                    diffs=dict(result.diffs or {}),
                    metrics=dict(result.metrics or {}),
                    latency_ms=result.latency_ms,
                    error_message=result.error_message,
                    created_at=result.created_at,
                )
                for result, case in rows
            ],
        )

    @staticmethod
    def _artifact_payload(run: AdaptationEvalRunRead, artifact: str) -> Any:
        if artifact == "case_results":
            return [item.model_dump(mode="json") for item in run.case_results]
        if artifact == "metrics":
            return run.summary_metrics or {}
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Артефакт экспорта неизвестен.",
        )

    @staticmethod
    async def export_run(
        run_id: str,
        export_format: str,
        artifact: AdaptationEvalExportArtifact,
        db: AsyncSession,
    ) -> tuple[str, str, str]:
        run = await AdminAdaptationEvalService.get_run(run_id, db)
        payload = AdminAdaptationEvalService._artifact_payload(run, artifact)
        if export_format == "json":
            return (
                f"adaptation-eval-{artifact}-{run.id}.json",
                "application/json; charset=utf-8",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        if export_format != "csv":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Формат экспорта неизвестен.",
            )

        output = StringIO()
        if artifact == "case_results":
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "case_external_id",
                    "scenario_type",
                    "status",
                    "capture_recall",
                    "retrieval_recall_at_k",
                    "retrieval_mrr",
                    "context_question_f1",
                    "context_issue_f1",
                    "overall_question_duplicate_rate",
                    "latency_ms",
                    "error_message",
                ],
            )
            writer.writeheader()
            for item in run.case_results:
                writer.writerow(
                    {
                        "case_external_id": item.case_external_id,
                        "scenario_type": item.scenario_type,
                        "status": item.status,
                        "capture_recall": item.metrics.get("capture_recall"),
                        "retrieval_recall_at_k": item.metrics.get(
                            "retrieval_recall_at_k"
                        ),
                        "retrieval_mrr": item.metrics.get("retrieval_mrr"),
                        "context_question_f1": item.metrics.get(
                            "context_question_f1"
                        ),
                        "context_issue_f1": item.metrics.get("context_issue_f1"),
                        "overall_question_duplicate_rate": item.metrics.get(
                            "overall_question_duplicate_rate"
                        ),
                        "latency_ms": item.latency_ms,
                        "error_message": item.error_message or "",
                    }
                )
        elif artifact == "metrics":
            writer = csv.DictWriter(output, fieldnames=["metric", "value"])
            writer.writeheader()
            for key, value in dict(payload).items():
                if isinstance(value, dict | list):
                    value = json.dumps(value, ensure_ascii=False)
                writer.writerow({"metric": key, "value": value})
        return (
            f"adaptation-eval-{artifact}-{run.id}.csv",
            "text/csv; charset=utf-8",
            output.getvalue(),
        )

    @staticmethod
    async def delete_run(run_id: str, actor: User, db: AsyncSession) -> None:
        run = await db.get(AdaptationEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-запуск не найден.",
            )
        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить Adaptation eval-запуск, который ещё выполняется.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.adaptation_eval_run_deleted",
            entity_type="adaptation_eval_run",
            entity_id=run.id,
            project_id=run.project_id,
        )
        await db.delete(run)
        await db.commit()

    @staticmethod
    async def delete_dataset(dataset_id: str, actor: User, db: AsyncSession) -> None:
        dataset = await db.get(AdaptationEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adaptation eval-набор не найден.",
            )
        active_runs = await db.scalar(
            select(func.count())
            .select_from(AdaptationEvalRun)
            .where(
                AdaptationEvalRun.dataset_id == dataset.id,
                AdaptationEvalRun.status.in_(["queued", "running"]),
            )
        )
        if active_runs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить набор, пока есть активные Adaptation eval-запуски.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.adaptation_eval_dataset_deleted",
            entity_type="adaptation_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
        )
        await db.delete(dataset)
        await db.commit()
