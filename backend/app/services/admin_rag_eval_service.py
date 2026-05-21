from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.qa_agent_graph import run_qa_agent_graph
from app.agents.rag_eval_judge_graph import run_rag_eval_judge_graph
from app.agents.rag_pipeline import run_rag_pipeline
from app.agents.rag_retrieval_graph import run_rag_retrieval_graph
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.llm_request_log import LLMRequestLog
from app.models.project import Project
from app.models.project_task_tag import ProjectTaskTag
from app.models.rag_eval import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalDataset,
    RagEvalDatasetTask,
    RagEvalIndexResult,
    RagEvalRun,
)
from app.models.task import Task, TaskAttachment, TaskStatus
from app.models.task_tag import TaskTag
from app.models.user import User
from app.schemas.admin_rag_eval import (
    RagEvalCaseImport,
    RagEvalCaseRead,
    RagEvalCaseResultRead,
    RagEvalDatasetDetailRead,
    RagEvalDatasetRead,
    RagEvalDatasetTaskRead,
    RagEvalExpectedRelevant,
    RagEvalImportPayload,
    RagEvalImportResultRead,
    RagEvalIndexResultRead,
    RagEvalRunConfig,
    RagEvalRunCreateRead,
    RagEvalRunListItemRead,
    RagEvalRunPageRead,
    RagEvalRunRead,
    RagEvalRunStatus,
    RagEvalStructuredImport,
    RagEvalTaskImport,
)
from app.services.attachment_content_service import AttachmentContentService
from app.services.audit_service import AuditService
from app.services.bm25_retrieval_service import BM25Document, BM25Index
from app.services.project_service import ProjectService
from app.services.rag_service import RagService
from app.services.task_service import TaskService
from app.services.task_tag_service import TaskTagService

_BM25_ATTACHMENT_SOURCE_TYPES = {"attachment_text", "attachment_image_alt_text"}
_BM25_CURRENT_TASK_CONTENT_SOURCE_TYPES = {"task_content"}
_BM25_CROSS_TASK_CONTEXT_SOURCE_TYPES = {
    "task_content",
    "attachment_text",
    "attachment_image_alt_text",
}


class AdminRagEvalService:
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
    def _parse_csv_payload(
        *,
        dataset_name: str | None,
        project_id: str | None,
        content: str | None,
    ) -> RagEvalStructuredImport:
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
        task_by_external_id: dict[str, RagEvalTaskImport] = {}
        cases: dict[str, RagEvalCaseImport] = {}
        for row in reader:
            task_external_id = AdminRagEvalService._normalize_text(row.get("task_external_id"))
            if not task_external_id:
                continue
            task_by_external_id[task_external_id] = RagEvalTaskImport(
                external_id=task_external_id,
                title=AdminRagEvalService._normalize_text(row.get("title")) or task_external_id,
                content=str(row.get("content") or ""),
                tags=AdminRagEvalService._split_multi(row.get("tags")),
                attachments=None,
            )
            case_external_id = AdminRagEvalService._normalize_text(row.get("case_external_id"))
            question = AdminRagEvalService._normalize_text(row.get("question"))
            if not case_external_id or not question:
                continue
            expected_task_ids = AdminRagEvalService._split_multi(
                row.get("expected_task_external_ids")
            )
            expected_texts = AdminRagEvalService._split_multi(row.get("expected_text_contains"))
            expected_relevant = [
                RagEvalExpectedRelevant(
                    task_external_id=expected_task_id or task_external_id,
                    text_contains=expected_texts[index] if index < len(expected_texts) else None,
                )
                for index, expected_task_id in enumerate(expected_task_ids or [task_external_id])
            ]
            cases[case_external_id] = RagEvalCaseImport(
                external_id=case_external_id,
                task_external_id=task_external_id,
                question=question,
                expected_answer=str(row.get("expected_answer") or "").strip() or None,
                expected_relevant=expected_relevant,
            )

        return RagEvalStructuredImport(
            dataset_name=dataset_name,
            project_id=project_id,
            tasks=list(task_by_external_id.values()),
            cases=list(cases.values()),
        )

    @staticmethod
    def _resolve_import_payload(payload: RagEvalImportPayload) -> RagEvalStructuredImport:
        if payload.format == "csv":
            return AdminRagEvalService._parse_csv_payload(
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
            return RagEvalStructuredImport.model_validate(decoded)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Для импорта нужен payload или content.",
        )

    @staticmethod
    async def _ensure_project_tags(
        project_id: str,
        raw_tags: list[str],
        actor: User,
        db: AsyncSession,
    ) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()
        for raw_tag in raw_tags:
            display_name = TaskTagService._normalize_display_name(raw_tag)
            if not display_name:
                continue
            normalized_name = TaskTagService._normalize_key(display_name)
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            tag = (
                await db.execute(select(TaskTag).where(TaskTag.normalized_name == normalized_name))
            ).scalar_one_or_none()
            if tag is None:
                tag = TaskTag(
                    name=display_name,
                    normalized_name=normalized_name,
                    created_by=actor.id,
                )
                db.add(tag)
                await db.flush()
            mapping = await db.get(
                ProjectTaskTag, {"project_id": project_id, "task_tag_id": tag.id}
            )
            if mapping is None:
                db.add(
                    ProjectTaskTag(
                        project_id=project_id,
                        task_tag_id=tag.id,
                        created_by=actor.id,
                    )
                )
            tags.append(tag.name)
        return tags

    @staticmethod
    def _safe_attachment_filename(filename: str) -> str:
        original = filename or "attachment.txt"
        safe_stem = re.sub(r"[^\w.-]+", "_", Path(original).stem).strip("._") or "attachment"
        suffix = Path(original).suffix or ".txt"
        return f"{uuid.uuid4().hex}_{safe_stem}{suffix}"

    @staticmethod
    def _delete_existing_attachment_file(storage_path: str, upload_root: Path) -> None:
        try:
            path = Path(storage_path)
            path.resolve().relative_to(upload_root.resolve())
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    @staticmethod
    async def _replace_text_attachments(
        *,
        project_id: str,
        task: Task,
        attachments: list[Any] | None,
        db: AsyncSession,
        warnings: list[str],
    ) -> None:
        if attachments is None:
            return

        settings = get_settings()
        upload_root = Path(settings.UPLOAD_DIR)
        existing = list(
            (await db.execute(select(TaskAttachment).where(TaskAttachment.task_id == task.id)))
            .scalars()
            .all()
        )
        for attachment in existing:
            AdminRagEvalService._delete_existing_attachment_file(
                attachment.storage_path,
                upload_root,
            )
            await db.delete(attachment)

        target_dir = upload_root / project_id / task.id
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in attachments:
            content_type = str(item.content_type or "text/plain")
            if not content_type.startswith("text/") and content_type not in {
                "application/json",
                "application/xml",
                "application/yaml",
                "application/x-yaml",
            }:
                warnings.append(f"Вложение {item.filename} пропущено: v1 импортирует только текст.")
                continue
            target_path = target_dir / AdminRagEvalService._safe_attachment_filename(item.filename)
            target_path.write_text(str(item.content), encoding="utf-8")
            db.add(
                TaskAttachment(
                    task_id=task.id,
                    filename=item.filename,
                    content_type=content_type,
                    storage_path=str(target_path),
                    alt_text=None,
                )
            )

    @staticmethod
    async def _upsert_dataset(
        data: RagEvalStructuredImport,
        actor: User,
        db: AsyncSession,
    ) -> RagEvalDataset:
        dataset = (
            await db.execute(
                select(RagEvalDataset).where(
                    RagEvalDataset.project_id == data.project_id,
                    RagEvalDataset.name == data.dataset_name,
                )
            )
        ).scalar_one_or_none()
        if dataset is None:
            dataset = RagEvalDataset(
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
    async def import_dataset(
        payload: RagEvalImportPayload,
        actor: User,
        db: AsyncSession,
    ) -> RagEvalImportResultRead:
        data = AdminRagEvalService._resolve_import_payload(payload)
        await ProjectService.get_project_or_404(data.project_id, db)

        dataset = await AdminRagEvalService._upsert_dataset(data, actor, db)
        existing_mappings = {
            item.external_id: item
            for item in (
                await db.execute(
                    select(RagEvalDatasetTask).where(RagEvalDatasetTask.dataset_id == dataset.id)
                )
            )
            .scalars()
            .all()
        }
        created_tasks = 0
        updated_tasks = 0
        warnings: list[str] = []
        task_id_by_external_id: dict[str, str] = {}

        for item in data.tasks:
            tags = await AdminRagEvalService._ensure_project_tags(
                data.project_id, item.tags, actor, db
            )
            mapping = existing_mappings.get(item.external_id)
            task = await db.get(Task, mapping.task_id) if mapping is not None else None
            if task is None:
                task = Task(
                    project_id=data.project_id,
                    title=item.title,
                    content=item.content,
                    tags=tags,
                    status=TaskStatus.DRAFT,
                    created_by=actor.id,
                    analyst_id=actor.id,
                )
                db.add(task)
                await db.flush()
                mapping = RagEvalDatasetTask(
                    dataset_id=dataset.id,
                    external_id=item.external_id,
                    task_id=task.id,
                )
                db.add(mapping)
                existing_mappings[item.external_id] = mapping
                created_tasks += 1
            else:
                task.title = item.title
                task.content = item.content
                task.tags = tags
                task.updated_at = datetime.now(UTC)
                task.validation_result = None
                updated_tasks += 1

            await AdminRagEvalService._replace_text_attachments(
                project_id=data.project_id,
                task=task,
                attachments=item.attachments,
                db=db,
                warnings=warnings,
            )
            task_id_by_external_id[item.external_id] = task.id

        existing_cases = {
            item.external_id: item
            for item in (
                await db.execute(select(RagEvalCase).where(RagEvalCase.dataset_id == dataset.id))
            )
            .scalars()
            .all()
        }
        for case in data.cases:
            task_id = task_id_by_external_id.get(case.task_external_id)
            if task_id is None:
                mapping = existing_mappings.get(case.task_external_id)
                task_id = mapping.task_id if mapping is not None else None
            if task_id is None:
                warnings.append(
                    f"Кейс {case.external_id} пропущен: задача {case.task_external_id} не найдена."
                )
                continue

            expected_relevant = [
                item.model_dump(mode="json", exclude_none=True) for item in case.expected_relevant
            ]
            row = existing_cases.get(case.external_id)
            if row is None:
                db.add(
                    RagEvalCase(
                        dataset_id=dataset.id,
                        external_id=case.external_id,
                        task_external_id=case.task_external_id,
                        task_id=task_id,
                        question=case.question,
                        expected_answer=case.expected_answer,
                        expected_relevant=expected_relevant,
                    )
                )
            else:
                row.task_external_id = case.task_external_id
                row.task_id = task_id
                row.question = case.question
                row.expected_answer = case.expected_answer
                row.expected_relevant = expected_relevant
                row.updated_at = datetime.now(UTC)

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.rag_eval_dataset_imported",
            entity_type="rag_eval_dataset",
            entity_id=dataset.id,
            project_id=data.project_id,
            metadata={
                "created_tasks": created_tasks,
                "updated_tasks": updated_tasks,
                "cases_total": len(data.cases),
            },
        )
        await db.commit()
        return RagEvalImportResultRead(
            dataset=await AdminRagEvalService.get_dataset(dataset.id, db),
            created_tasks=created_tasks,
            updated_tasks=updated_tasks,
            imported_cases=len(data.cases),
            warnings=warnings,
        )

    @staticmethod
    async def list_datasets(db: AsyncSession) -> list[RagEvalDatasetRead]:
        datasets = list(
            (
                await db.execute(
                    select(RagEvalDataset, Project.name)
                    .join(Project, Project.id == RagEvalDataset.project_id)
                    .order_by(RagEvalDataset.updated_at.desc())
                )
            ).all()
        )
        result: list[RagEvalDatasetRead] = []
        for dataset, project_name in datasets:
            result.append(
                await AdminRagEvalService._serialize_dataset(dataset, db, project_name=project_name)
            )
        return result

    @staticmethod
    async def _serialize_dataset(
        dataset: RagEvalDataset,
        db: AsyncSession,
        *,
        project_name: str | None = None,
    ) -> RagEvalDatasetRead:
        tasks_total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(RagEvalDatasetTask)
                    .where(RagEvalDatasetTask.dataset_id == dataset.id)
                )
            ).scalar_one()
        )
        cases_total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(RagEvalCase)
                    .where(RagEvalCase.dataset_id == dataset.id)
                )
            ).scalar_one()
        )
        last_run = (
            await db.execute(
                select(RagEvalRun)
                .where(RagEvalRun.dataset_id == dataset.id)
                .order_by(RagEvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return RagEvalDatasetRead(
            id=dataset.id,
            project_id=dataset.project_id,
            project_name=project_name,
            name=dataset.name,
            tasks_total=tasks_total,
            cases_total=cases_total,
            last_run_id=last_run.id if last_run is not None else None,
            last_run_status=last_run.status if last_run is not None else None,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    @staticmethod
    async def get_dataset(dataset_id: str, db: AsyncSession) -> RagEvalDatasetDetailRead:
        dataset = await db.get(RagEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-набор не найден."
            )
        project = await db.get(Project, dataset.project_id)
        base = await AdminRagEvalService._serialize_dataset(
            dataset,
            db,
            project_name=project.name if project is not None else None,
        )
        task_rows = list(
            (
                await db.execute(
                    select(RagEvalDatasetTask, Task)
                    .join(Task, Task.id == RagEvalDatasetTask.task_id)
                    .where(RagEvalDatasetTask.dataset_id == dataset.id)
                    .order_by(RagEvalDatasetTask.external_id.asc())
                )
            ).all()
        )
        case_rows = list(
            (
                await db.execute(
                    select(RagEvalCase)
                    .where(RagEvalCase.dataset_id == dataset.id)
                    .order_by(RagEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        return RagEvalDatasetDetailRead(
            **base.model_dump(),
            tasks=[
                RagEvalDatasetTaskRead(
                    id=mapping.id,
                    external_id=mapping.external_id,
                    task_id=mapping.task_id,
                    title=task.title,
                    updated_at=mapping.updated_at,
                )
                for mapping, task in task_rows
            ],
            cases=[
                RagEvalCaseRead(
                    id=item.id,
                    external_id=item.external_id,
                    task_external_id=item.task_external_id,
                    task_id=item.task_id,
                    question=item.question,
                    expected_answer=item.expected_answer,
                    expected_relevant=list(item.expected_relevant or []),
                    updated_at=item.updated_at,
                )
                for item in case_rows
            ],
        )

    @staticmethod
    async def create_run(
        dataset_id: str,
        config: RagEvalRunConfig,
        actor: User,
        db: AsyncSession,
    ) -> RagEvalRunCreateRead:
        dataset = await db.get(RagEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-набор не найден."
            )
        run = RagEvalRun(
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
            event_type="admin.rag_eval_run_created",
            entity_type="rag_eval_run",
            entity_id=run.id,
            project_id=dataset.project_id,
            metadata={"dataset_id": dataset.id},
        )
        await db.commit()
        await db.refresh(run)
        return RagEvalRunCreateRead(
            id=run.id,
            dataset_id=run.dataset_id,
            status=run.status,
            config=RagEvalRunConfig.model_validate(run.config),
            created_at=run.created_at,
        )

    @staticmethod
    def _expected_matches_chunk(
        expected: dict[str, Any],
        chunk: dict[str, Any],
        task_id_by_external_id: dict[str, str],
    ) -> bool:
        expected_task_external_id = str(expected.get("task_external_id") or "").strip()
        if expected_task_external_id:
            expected_task_id = task_id_by_external_id.get(expected_task_external_id)
            if expected_task_id and str(chunk.get("task_id") or "") != expected_task_id:
                return False
        source_type = str(expected.get("source_type") or "").strip()
        if source_type and str(chunk.get("source_type") or "") != source_type:
            return False
        if expected.get("chunk_index") is not None:
            try:
                if int(chunk.get("chunk_index")) != int(expected["chunk_index"]):
                    return False
            except (TypeError, ValueError):
                return False
        text_contains = str(expected.get("text_contains") or "").strip().casefold()
        if text_contains:
            content = str(chunk.get("content") or "").casefold()
            if text_contains not in content:
                return False
        return True

    @staticmethod
    def _case_metrics(
        *,
        expected_relevant: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        task_id_by_external_id: dict[str, str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        matched_expected: list[dict[str, Any]] = []
        first_rank: int | None = None
        for expected in expected_relevant:
            for index, chunk in enumerate(retrieved_chunks, start=1):
                if AdminRagEvalService._expected_matches_chunk(
                    expected, chunk, task_id_by_external_id
                ):
                    matched_expected.append(
                        {**expected, "rank": index, "chunk_id": chunk.get("chunk_id")}
                    )
                    if first_rank is None or index < first_rank:
                        first_rank = index
                    break
        has_expected = bool(expected_relevant)
        return (
            {
                "has_expected": has_expected,
                "matched": bool(matched_expected),
                "first_relevant_rank": first_rank,
                "recall_at_1": bool(first_rank is not None and first_rank <= 1),
                "recall_at_3": bool(first_rank is not None and first_rank <= 3),
                "recall_at_5": bool(first_rank is not None and first_rank <= 5),
                "mrr": round(1 / first_rank, 4) if first_rank else 0,
                "no_context": len(retrieved_chunks) == 0,
                "chunks_above_threshold": sum(
                    bool(chunk.get("score", 0) >= chunk.get("threshold", 0))
                    for chunk in retrieved_chunks
                    if chunk.get("threshold") is not None
                ),
            },
            matched_expected,
        )

    @staticmethod
    def _precision_at_k(
        *,
        expected_relevant: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        task_id_by_external_id: dict[str, str],
        k: int,
    ) -> float:
        if k <= 0:
            return 0
        relevant_retrieved = 0
        for chunk in retrieved_chunks[:k]:
            if any(
                AdminRagEvalService._expected_matches_chunk(
                    expected,
                    chunk,
                    task_id_by_external_id,
                )
                for expected in expected_relevant
            ):
                relevant_retrieved += 1
        return round(relevant_retrieved / k, 4)

    @staticmethod
    def _bm25_metrics(
        *,
        expected_relevant: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        task_id_by_external_id: dict[str, str],
        k: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        metrics, matched_expected = AdminRagEvalService._case_metrics(
            expected_relevant=expected_relevant,
            retrieved_chunks=retrieved_chunks,
            task_id_by_external_id=task_id_by_external_id,
        )
        return (
            {
                "bm25_matched": metrics["matched"],
                "bm25_first_relevant_rank": metrics["first_relevant_rank"],
                "bm25_recall_at_1": metrics["recall_at_1"],
                "bm25_recall_at_3": metrics["recall_at_3"],
                "bm25_recall_at_5": metrics["recall_at_5"],
                "bm25_precision_at_k": AdminRagEvalService._precision_at_k(
                    expected_relevant=expected_relevant,
                    retrieved_chunks=retrieved_chunks,
                    task_id_by_external_id=task_id_by_external_id,
                    k=k,
                ),
                "bm25_mrr": metrics["mrr"],
                "bm25_no_context": metrics["no_context"],
                "bm25_retrieved_chunks": retrieved_chunks,
            },
            matched_expected,
        )

    @staticmethod
    async def _build_bm25_index(
        *,
        dataset_tasks: list[tuple[RagEvalDatasetTask, Task]],
        actor_user_id: str,
        db: AsyncSession,
    ) -> BM25Index:
        documents: list[BM25Document] = []
        for mapping, task in dataset_tasks:
            attachments = await TaskService._get_attachments(task.id, db)
            attachment_payloads = await AttachmentContentService.build_attachment_payloads(
                db,
                task,
                attachments,
                actor_user_id=actor_user_id,
                allow_vision=False,
            )
            rag_index = await run_rag_pipeline(
                db=db,
                actor_user_id=actor_user_id,
                task_id=task.id,
                project_id=task.project_id,
                title=task.title,
                content=task.content,
                tags=task.tags,
                attachments=attachment_payloads,
                validation_result=task.validation_result,
            )
            for chunk in list(rag_index.get("chunks", [])):
                content = str(chunk.get("content") or "").strip()
                if not content:
                    continue
                documents.append(
                    BM25Document(
                        content=content,
                        metadata={
                            "chunk_id": str(chunk.get("chunk_id") or ""),
                            "id": str(chunk.get("chunk_id") or ""),
                            "scope": "bm25",
                            "task_id": task.id,
                            "task_external_id": mapping.external_id,
                            "task_title": task.title,
                            "source_type": str(chunk.get("source_type") or "") or None,
                            "chunk_kind": str(chunk.get("chunk_kind") or "") or None,
                            "chunk_index": chunk.get("chunk_index"),
                            "filename": chunk.get("filename"),
                        },
                    )
                )
        return BM25Index(documents)

    @staticmethod
    def _bm25_include_document(
        *,
        document: BM25Document,
        task_id: str,
        config: RagEvalRunConfig,
    ) -> bool:
        metadata = document.metadata
        source_type = str(metadata.get("source_type") or "")
        chunk_kind = str(metadata.get("chunk_kind") or "")
        document_task_id = str(metadata.get("task_id") or "")
        source_types = {source_type, chunk_kind}
        if document_task_id == task_id:
            current_task_source_types = set(_BM25_ATTACHMENT_SOURCE_TYPES)
            if config.include_current_task_content:
                current_task_source_types.update(_BM25_CURRENT_TASK_CONTENT_SOURCE_TYPES)
            return bool(source_types & current_task_source_types)
        return bool(
            config.include_cross_task and source_types & _BM25_CROSS_TASK_CONTEXT_SOURCE_TYPES
        )

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
        return ordered[index]

    @staticmethod
    async def process_run(run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(RagEvalRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await db.commit()
            started = perf_counter()
            try:
                await AdminRagEvalService._process_run_inner(run.id, db)
                run = await db.get(RagEvalRun, run_id)
                if run is not None:
                    run.status = "success"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.summary_metrics = await AdminRagEvalService._summarize_run(run, db)
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                run = await db.get(RagEvalRun, run_id)
                if run is not None:
                    run.status = "error"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.error_message = str(exc)[:1000]
                    await db.commit()

    @staticmethod
    async def _process_run_inner(run_id: str, db: AsyncSession) -> None:
        run = await db.get(RagEvalRun, run_id)
        if run is None:
            return
        config = RagEvalRunConfig.model_validate(run.config)
        dataset_tasks = list(
            (
                await db.execute(
                    select(RagEvalDatasetTask, Task)
                    .join(Task, Task.id == RagEvalDatasetTask.task_id)
                    .where(RagEvalDatasetTask.dataset_id == run.dataset_id)
                    .order_by(RagEvalDatasetTask.external_id.asc())
                )
            ).all()
        )
        task_id_by_external_id = {mapping.external_id: task.id for mapping, task in dataset_tasks}
        bm25_index = (
            await AdminRagEvalService._build_bm25_index(
                dataset_tasks=dataset_tasks,
                actor_user_id=run.created_by,
                db=db,
            )
            if config.run_bm25_baseline
            else None
        )

        if config.indexing_mode != "none":
            for mapping, task in dataset_tasks:
                should_index = config.indexing_mode == "all" or TaskService._has_stale_embeddings(
                    task
                )
                if not should_index:
                    continue
                attachments = await TaskService._get_attachments(task.id, db)
                try:
                    index_result = await RagService.index_task_context_with_metrics(
                        db,
                        task,
                        attachments,
                        actor_user_id=run.created_by,
                        allow_vision=False,
                        validation_result=task.validation_result,
                    )
                    db.add(
                        RagEvalIndexResult(
                            run_id=run.id,
                            task_id=task.id,
                            task_external_id=mapping.external_id,
                            status="success" if index_result["indexed"] else "error",
                            attachment_payload_ms=index_result["attachment_payload_ms"],
                            chunking_ms=index_result["chunking_ms"],
                            embedding_and_qdrant_write_ms=index_result[
                                "embedding_and_qdrant_write_ms"
                            ],
                            qdrant_cleanup_ms=index_result["qdrant_cleanup_ms"],
                            total_index_ms=index_result["total_index_ms"],
                            chunks_total=index_result["chunks_total"],
                            error_message=None
                            if index_result["indexed"]
                            else "Qdrant indexing returned false.",
                        )
                    )
                    await db.commit()
                except Exception as exc:  # noqa: BLE001
                    db.add(
                        RagEvalIndexResult(
                            run_id=run.id,
                            task_id=task.id,
                            task_external_id=mapping.external_id,
                            status="error",
                            chunks_total=0,
                            error_message=str(exc)[:1000],
                        )
                    )
                    await db.commit()

        cases = list(
            (
                await db.execute(
                    select(RagEvalCase)
                    .where(RagEvalCase.dataset_id == run.dataset_id)
                    .order_by(RagEvalCase.external_id.asc())
                )
            )
            .scalars()
            .all()
        )
        for case in cases:
            await AdminRagEvalService._run_case(
                run=run,
                case=case,
                config=config,
                task_id_by_external_id=task_id_by_external_id,
                bm25_index=bm25_index,
                db=db,
            )

    @staticmethod
    async def _run_case(
        *,
        run: RagEvalRun,
        case: RagEvalCase,
        config: RagEvalRunConfig,
        task_id_by_external_id: dict[str, str],
        bm25_index: BM25Index | None,
        db: AsyncSession,
    ) -> None:
        task = await db.get(Task, case.task_id)
        if task is None:
            db.add(
                RagEvalCaseResult(
                    run_id=run.id,
                    case_id=case.id,
                    status="error",
                    retrieved_chunks=[],
                    matched_expected=[],
                    metrics={},
                    error_message="Anchor task not found.",
                )
            )
            await db.commit()
            return

        case_started = perf_counter()
        answer_text: str | None = None
        answer_source_ref: dict[str, Any] | None = None
        judge_payload: dict[str, Any] | None = None
        error_message: str | None = None
        answer_latency_ms: int | None = None
        judge_latency_ms: int | None = None
        try:
            retrieval_started = perf_counter()
            retrieval_state = await run_rag_retrieval_graph(
                db=db,
                actor_user_id=run.created_by,
                task_id=task.id,
                project_id=run.project_id,
                task_title=task.title,
                task_status=task.status.value,
                task_content=task.content,
                task_tags=list(task.tags),
                question=case.question,
                retrieval_limit=config.retrieval_limit,
                use_query_rewriter=config.use_query_rewriter,
                use_hybrid_rerank=config.use_hybrid_rerank,
                include_cross_task=config.include_cross_task,
                include_current_task_content=config.include_current_task_content,
                min_score_override=config.min_score_override,
            )
            retrieval_latency_ms = int((perf_counter() - retrieval_started) * 1000)
            retrieved_chunks = list(retrieval_state.get("reranked_chunks", []))[
                : config.retrieval_limit
            ]

            if config.run_answer_agent:
                answer_started = perf_counter()
                qa_state = await run_qa_agent_graph(
                    db=db,
                    actor_user_id=run.created_by,
                    task_id=task.id,
                    project_id=run.project_id,
                    task_title=task.title,
                    task_status=task.status.value,
                    task_content=task.content,
                    message_content=case.question,
                    validation_result=task.validation_result,
                    related_tasks=[],
                    routing_mode="rag_eval",
                    use_query_rewriter=config.use_query_rewriter,
                    use_hybrid_rerank=config.use_hybrid_rerank,
                    include_cross_task=config.include_cross_task,
                    include_current_task_content=config.include_current_task_content,
                    min_score_override=config.min_score_override,
                )
                answer_latency_ms = int((perf_counter() - answer_started) * 1000)
                answer_text = str(qa_state.get("response", ""))
                answer_source_ref = dict(qa_state.get("source_ref", {}))

            if config.run_llm_judge and answer_text:
                judge_started = perf_counter()
                judge_state = await run_rag_eval_judge_graph(
                    db=db,
                    actor_user_id=run.created_by,
                    task_id=task.id,
                    project_id=run.project_id,
                    question=case.question,
                    expected_answer=case.expected_answer,
                    answer_text=answer_text,
                    retrieved_chunks=retrieved_chunks,
                )
                judge_latency_ms = int((perf_counter() - judge_started) * 1000)
                judge_payload = dict(judge_state.get("judge_payload", {}))

            metrics, matched_expected = AdminRagEvalService._case_metrics(
                expected_relevant=list(case.expected_relevant or []),
                retrieved_chunks=retrieved_chunks,
                task_id_by_external_id=task_id_by_external_id,
            )
            if bm25_index is not None:
                bm25_retrieved_chunks = bm25_index.search(
                    case.question,
                    limit=config.retrieval_limit,
                    include_document=lambda document: AdminRagEvalService._bm25_include_document(
                        document=document,
                        task_id=task.id,
                        config=config,
                    ),
                )
                bm25_metrics, bm25_matched_expected = AdminRagEvalService._bm25_metrics(
                    expected_relevant=list(case.expected_relevant or []),
                    retrieved_chunks=bm25_retrieved_chunks,
                    task_id_by_external_id=task_id_by_external_id,
                    k=config.retrieval_limit,
                )
                metrics.update(bm25_metrics)
                metrics["bm25_matched_expected"] = bm25_matched_expected
                metrics["rag_vs_bm25_mrr_delta"] = round(
                    float(metrics.get("mrr") or 0) - float(bm25_metrics.get("bm25_mrr") or 0),
                    4,
                )
            if answer_source_ref is not None:
                metrics["answer_confidence"] = answer_source_ref.get("answer_confidence")
            if judge_payload is not None:
                metrics["groundedness"] = judge_payload.get("groundedness")
                metrics["correctness"] = judge_payload.get("correctness")
            result_status = "success"
        except Exception as exc:  # noqa: BLE001
            retrieval_latency_ms = None
            retrieved_chunks = []
            matched_expected = []
            metrics = {}
            error_message = str(exc)[:1000]
            result_status = "error"

        db.add(
            RagEvalCaseResult(
                run_id=run.id,
                case_id=case.id,
                status=result_status,
                retrieved_chunks=retrieved_chunks,
                matched_expected=matched_expected,
                answer_text=answer_text,
                answer_source_ref=answer_source_ref,
                judge_payload=judge_payload,
                metrics=metrics,
                latency_ms=int((perf_counter() - case_started) * 1000),
                retrieval_latency_ms=retrieval_latency_ms,
                answer_latency_ms=answer_latency_ms,
                judge_latency_ms=judge_latency_ms,
                error_message=error_message,
            )
        )
        await db.commit()

    @staticmethod
    async def _summarize_run(run: RagEvalRun, db: AsyncSession) -> dict[str, Any]:
        case_results = list(
            (await db.execute(select(RagEvalCaseResult).where(RagEvalCaseResult.run_id == run.id)))
            .scalars()
            .all()
        )
        index_results = list(
            (
                await db.execute(
                    select(RagEvalIndexResult).where(RagEvalIndexResult.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
        successful = [item for item in case_results if item.status == "success"]
        with_expected = [item for item in successful if item.metrics.get("has_expected")]
        denominator = max(len(with_expected), 1)
        bm25_with_expected = [
            item
            for item in with_expected
            if "bm25_mrr" in item.metrics or "bm25_recall_at_5" in item.metrics
        ]
        bm25_denominator = max(len(bm25_with_expected), 1)
        first_ranks = [
            int(item.metrics["first_relevant_rank"])
            for item in with_expected
            if item.metrics.get("first_relevant_rank") is not None
        ]
        groundedness: dict[str, int] = {}
        correctness: dict[str, int] = {}
        for item in successful:
            if item.metrics.get("groundedness"):
                key = str(item.metrics["groundedness"])
                groundedness[key] = groundedness.get(key, 0) + 1
            if item.metrics.get("correctness"):
                key = str(item.metrics["correctness"])
                correctness[key] = correctness.get(key, 0) + 1

        token_stmt = select(
            func.sum(LLMRequestLog.prompt_tokens),
            func.sum(LLMRequestLog.completion_tokens),
            func.sum(LLMRequestLog.total_tokens),
            func.sum(LLMRequestLog.estimated_cost_usd),
        ).where(
            LLMRequestLog.created_at >= run.started_at,
            LLMRequestLog.project_id == run.project_id,
        )
        if run.finished_at is not None:
            token_stmt = token_stmt.where(LLMRequestLog.created_at <= run.finished_at)
        prompt_tokens, completion_tokens, total_tokens, estimated_cost = (
            await db.execute(token_stmt)
        ).one()

        retrieval_latencies = [
            item.retrieval_latency_ms
            for item in successful
            if item.retrieval_latency_ms is not None
        ]
        index_latencies = [
            item.total_index_ms for item in index_results if item.total_index_ms is not None
        ]
        return {
            "cases_total": len(case_results),
            "case_errors_total": len([item for item in case_results if item.status == "error"]),
            "cases_with_expected_total": len(with_expected),
            "recall_at_1": round(
                sum(bool(item.metrics.get("recall_at_1")) for item in with_expected) / denominator,
                4,
            ),
            "recall_at_3": round(
                sum(bool(item.metrics.get("recall_at_3")) for item in with_expected) / denominator,
                4,
            ),
            "recall_at_5": round(
                sum(bool(item.metrics.get("recall_at_5")) for item in with_expected) / denominator,
                4,
            ),
            "mrr": round(
                sum(float(item.metrics.get("mrr") or 0) for item in with_expected) / denominator, 4
            ),
            "bm25_recall_at_5": round(
                sum(bool(item.metrics.get("bm25_recall_at_5")) for item in bm25_with_expected)
                / bm25_denominator,
                4,
            )
            if bm25_with_expected
            else None,
            "bm25_precision_at_k": round(
                sum(
                    float(item.metrics.get("bm25_precision_at_k") or 0)
                    for item in bm25_with_expected
                )
                / bm25_denominator,
                4,
            )
            if bm25_with_expected
            else None,
            "bm25_mrr": round(
                sum(float(item.metrics.get("bm25_mrr") or 0) for item in bm25_with_expected)
                / bm25_denominator,
                4,
            )
            if bm25_with_expected
            else None,
            "rag_vs_bm25_mrr_delta": round(
                (
                    sum(float(item.metrics.get("mrr") or 0) for item in bm25_with_expected)
                    - sum(float(item.metrics.get("bm25_mrr") or 0) for item in bm25_with_expected)
                )
                / bm25_denominator,
                4,
            )
            if bm25_with_expected
            else None,
            "no_context_rate": round(
                sum(bool(item.metrics.get("no_context")) for item in successful)
                / max(len(successful), 1),
                4,
            ),
            "avg_first_relevant_rank": (
                round(sum(first_ranks) / len(first_ranks), 2) if first_ranks else None
            ),
            "groundedness": groundedness,
            "correctness": correctness,
            "p50_retrieval_latency_ms": AdminRagEvalService._percentile(retrieval_latencies, 0.5),
            "p95_retrieval_latency_ms": AdminRagEvalService._percentile(retrieval_latencies, 0.95),
            "p50_index_latency_ms": AdminRagEvalService._percentile(index_latencies, 0.5),
            "p95_index_latency_ms": AdminRagEvalService._percentile(index_latencies, 0.95),
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int(total_tokens or 0),
            "estimated_cost_usd": float(estimated_cost) if estimated_cost is not None else None,
        }

    @staticmethod
    async def list_runs(
        dataset_id: str,
        db: AsyncSession,
        *,
        run_status: RagEvalRunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RagEvalRunPageRead:
        dataset = await db.get(RagEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-набор не найден."
            )

        conditions = [RagEvalRun.dataset_id == dataset.id]
        if run_status is not None:
            conditions.append(RagEvalRun.status == run_status)

        total = await db.scalar(select(func.count()).select_from(RagEvalRun).where(*conditions))
        runs = list(
            (
                await db.execute(
                    select(RagEvalRun)
                    .where(*conditions)
                    .order_by(RagEvalRun.created_at.desc())
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return RagEvalRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[
                RagEvalRunListItemRead(
                    id=run.id,
                    dataset_id=run.dataset_id,
                    dataset_name=dataset.name,
                    project_id=run.project_id,
                    status=cast(RagEvalRunStatus, run.status),
                    config=RagEvalRunConfig.model_validate(run.config),
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
    async def get_run(run_id: str, db: AsyncSession) -> RagEvalRunRead:
        run = await db.get(RagEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-запуск не найден."
            )
        dataset = await db.get(RagEvalDataset, run.dataset_id)
        index_results = list(
            (
                await db.execute(
                    select(RagEvalIndexResult)
                    .where(RagEvalIndexResult.run_id == run.id)
                    .order_by(RagEvalIndexResult.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        case_rows = list(
            (
                await db.execute(
                    select(RagEvalCaseResult, RagEvalCase)
                    .join(RagEvalCase, RagEvalCase.id == RagEvalCaseResult.case_id)
                    .where(RagEvalCaseResult.run_id == run.id)
                    .order_by(RagEvalCase.external_id.asc())
                )
            ).all()
        )
        return RagEvalRunRead(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset.name if dataset is not None else None,
            project_id=run.project_id,
            status=run.status,
            config=RagEvalRunConfig.model_validate(run.config),
            summary_metrics=run.summary_metrics,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            created_at=run.created_at,
            index_results=[
                RagEvalIndexResultRead(
                    id=item.id,
                    task_id=item.task_id,
                    task_external_id=item.task_external_id,
                    status=item.status,
                    attachment_payload_ms=item.attachment_payload_ms,
                    chunking_ms=item.chunking_ms,
                    embedding_and_qdrant_write_ms=item.embedding_and_qdrant_write_ms,
                    qdrant_cleanup_ms=item.qdrant_cleanup_ms,
                    total_index_ms=item.total_index_ms,
                    chunks_total=item.chunks_total,
                    error_message=item.error_message,
                    created_at=item.created_at,
                )
                for item in index_results
            ],
            case_results=[
                RagEvalCaseResultRead(
                    id=result.id,
                    case_id=result.case_id,
                    case_external_id=case.external_id,
                    question=case.question,
                    task_id=case.task_id,
                    task_external_id=case.task_external_id,
                    status=result.status,
                    retrieved_chunks=list(result.retrieved_chunks or []),
                    matched_expected=list(result.matched_expected or []),
                    answer_text=result.answer_text,
                    answer_source_ref=result.answer_source_ref,
                    judge_payload=result.judge_payload,
                    metrics=dict(result.metrics or {}),
                    latency_ms=result.latency_ms,
                    retrieval_latency_ms=result.retrieval_latency_ms,
                    answer_latency_ms=result.answer_latency_ms,
                    judge_latency_ms=result.judge_latency_ms,
                    error_message=result.error_message,
                    created_at=result.created_at,
                )
                for result, case in case_rows
            ],
        )

    @staticmethod
    async def export_run(run_id: str, export_format: str, db: AsyncSession) -> tuple[str, str, str]:
        run = await AdminRagEvalService.get_run(run_id, db)
        if export_format == "json":
            return (
                f"rag-eval-{run.id}.json",
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
                "question",
                "status",
                "recall_at_1",
                "recall_at_3",
                "recall_at_5",
                "mrr",
                "bm25_recall_at_5",
                "bm25_precision_at_k",
                "bm25_mrr",
                "bm25_first_relevant_rank",
                "rag_vs_bm25_mrr_delta",
                "groundedness",
                "correctness",
                "retrieval_latency_ms",
                "answer_latency_ms",
                "judge_latency_ms",
                "answer_text",
            ],
        )
        writer.writeheader()
        for item in run.case_results:
            writer.writerow(
                {
                    "case_external_id": item.case_external_id,
                    "question": item.question,
                    "status": item.status,
                    "recall_at_1": item.metrics.get("recall_at_1"),
                    "recall_at_3": item.metrics.get("recall_at_3"),
                    "recall_at_5": item.metrics.get("recall_at_5"),
                    "mrr": item.metrics.get("mrr"),
                    "bm25_recall_at_5": item.metrics.get("bm25_recall_at_5"),
                    "bm25_precision_at_k": item.metrics.get("bm25_precision_at_k"),
                    "bm25_mrr": item.metrics.get("bm25_mrr"),
                    "bm25_first_relevant_rank": item.metrics.get("bm25_first_relevant_rank"),
                    "rag_vs_bm25_mrr_delta": item.metrics.get("rag_vs_bm25_mrr_delta"),
                    "groundedness": item.metrics.get("groundedness"),
                    "correctness": item.metrics.get("correctness"),
                    "retrieval_latency_ms": item.retrieval_latency_ms,
                    "answer_latency_ms": item.answer_latency_ms,
                    "judge_latency_ms": item.judge_latency_ms,
                    "answer_text": item.answer_text or "",
                }
            )
        return f"rag-eval-{run.id}.csv", "text/csv; charset=utf-8", output.getvalue()

    @staticmethod
    async def delete_run(run_id: str, actor: User, db: AsyncSession) -> None:
        run = await db.get(RagEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-запуск не найден."
            )
        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить RAG eval-запуск, который ещё выполняется.",
            )

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.rag_eval_run_deleted",
            entity_type="rag_eval_run",
            entity_id=run.id,
            project_id=run.project_id,
            metadata={"dataset_id": run.dataset_id, "status": run.status},
        )
        await db.delete(run)
        await db.commit()

    @staticmethod
    async def delete_dataset(dataset_id: str, actor: User, db: AsyncSession) -> None:
        dataset = await db.get(RagEvalDataset, dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="RAG eval-набор не найден."
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.rag_eval_dataset_deleted",
            entity_type="rag_eval_dataset",
            entity_id=dataset.id,
            project_id=dataset.project_id,
        )
        await db.delete(dataset)
        await db.commit()
