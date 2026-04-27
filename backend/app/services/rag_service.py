from __future__ import annotations

from datetime import UTC, datetime
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
        if attachment_payloads is None:
            attachment_payloads = await AttachmentContentService.build_attachment_payloads(
                db,
                task,
                attachments,
                actor_user_id=actor_user_id,
                allow_vision=allow_vision,
            )
        rag_index = await run_rag_pipeline(
            task_id=task.id,
            title=task.title,
            content=task.content,
            tags=task.tags,
            attachments=attachment_payloads,
            validation_result=validation_result,
        )
        indexed = await QdrantService.replace_task_knowledge(
            task_id=task.id,
            project_id=task.project_id,
            task_title=task.title,
            task_status=task.status.value,
            tags=list(task.tags),
            chunks=list(rag_index.get("chunks", [])),
        )
        task.indexed_at = datetime.now(UTC) if indexed else None
        return list(rag_index.get("chunk_ids", [])) if indexed else []
