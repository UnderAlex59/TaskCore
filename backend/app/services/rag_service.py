from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_pipeline import run_rag_pipeline
from app.models.task import Task, TaskAttachment
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
        task: Task,
        attachments: list[TaskAttachment],
        *,
        validation_result: dict | None = None,
    ) -> list[str]:
        rag_index = await run_rag_pipeline(
            task_id=task.id,
            title=task.title,
            content=task.content,
            tags=task.tags,
            attachments=[
                {
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "basename": Path(item.storage_path).name,
                }
                for item in attachments
            ],
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
        task.indexed_at = datetime.now(timezone.utc) if indexed else None
        return list(rag_index.get("chunk_ids", [])) if indexed else []
