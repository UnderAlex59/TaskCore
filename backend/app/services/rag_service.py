from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_pipeline import run_rag_pipeline
from app.models.task import Task, TaskAttachment
from app.services.attachment_content_service import AttachmentContentService
from app.services.qdrant_service import QdrantService


class RagService:
    @staticmethod
    async def search_related_tasks(
        db: AsyncSession,
        *,
        project_id: str,
        query_text: str,
        exclude_task_id: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, str | int | float]]:
        semantic_matches = await QdrantService.search_related_tasks(
            project_id=project_id,
            query_text=query_text,
            exclude_task_id=exclude_task_id,
            limit=limit,
        )
        if not semantic_matches:
            return []

        return [
            {
                "task_id": str(item["task_id"]),
                "title": str(item["title"]),
                "status": str(item["status"]),
                "score": float(item["score"]),
            }
            for item in semantic_matches
        ]

    @staticmethod
    async def index_task_context(
        db: AsyncSession,
        task: Task,
        attachments: list[TaskAttachment],
        *,
        actor_user_id: str | None = None,
        attachment_payloads: list[dict[str, Any]] | None = None,
        allow_vision: bool = True,
        validation_result: dict | None = None,
    ) -> list[str]:
        result = await RagService.index_task_context_with_metrics(
            db,
            task,
            attachments,
            actor_user_id=actor_user_id,
            attachment_payloads=attachment_payloads,
            allow_vision=allow_vision,
            validation_result=validation_result,
        )
        return list(result["chunk_ids"])

    @staticmethod
    async def index_task_context_with_metrics(
        db: AsyncSession,
        task: Task,
        attachments: list[TaskAttachment],
        *,
        actor_user_id: str | None = None,
        attachment_payloads: list[dict[str, Any]] | None = None,
        allow_vision: bool = True,
        validation_result: dict | None = None,
    ) -> dict[str, Any]:
        total_started = perf_counter()
        attachment_payload_ms: int | None = None
        if attachment_payloads is None:
            attachments_started = perf_counter()
            attachment_payloads = await AttachmentContentService.build_attachment_payloads(
                db,
                task,
                attachments,
                actor_user_id=actor_user_id,
                allow_vision=allow_vision,
            )
            attachment_payload_ms = int((perf_counter() - attachments_started) * 1000)

        chunking_started = perf_counter()
        rag_index = await run_rag_pipeline(
            db=db,
            actor_user_id=actor_user_id,
            task_id=task.id,
            project_id=task.project_id,
            title=task.title,
            content=task.content,
            tags=task.tags,
            attachments=attachment_payloads,
            validation_result=validation_result,
        )
        chunking_ms = int((perf_counter() - chunking_started) * 1000)
        write_started = perf_counter()
        indexed = await QdrantService.replace_task_knowledge(
            task_id=task.id,
            project_id=task.project_id,
            task_title=task.title,
            task_status=task.status.value,
            tags=list(task.tags),
            chunks=list(rag_index.get("chunks", [])),
        )
        embedding_and_qdrant_write_ms = int((perf_counter() - write_started) * 1000)
        task.indexed_at = datetime.now(UTC) if indexed else None
        chunk_ids = list(rag_index.get("chunk_ids", [])) if indexed else []
        return {
            "chunk_ids": chunk_ids,
            "indexed": indexed,
            "attachment_payload_ms": attachment_payload_ms,
            "chunking_ms": chunking_ms,
            "embedding_and_qdrant_write_ms": embedding_and_qdrant_write_ms,
            "qdrant_cleanup_ms": None,
            "total_index_ms": int((perf_counter() - total_started) * 1000),
            "chunks_total": len(chunk_ids),
        }
