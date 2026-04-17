from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_pipeline import run_rag_pipeline
from app.models.task import Task, TaskAttachment


class RagService:
    @staticmethod
    def _tokenize(value: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-zА-Яа-я0-9_]{4,}", value.lower())}

    @staticmethod
    async def search_related_tasks(
        db: AsyncSession,
        *,
        project_id: str,
        query_text: str,
        exclude_task_id: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, str | int]]:
        stmt: Select[tuple[Task]] = select(Task).where(Task.project_id == project_id).order_by(Task.updated_at.desc())
        if exclude_task_id is not None:
            stmt = stmt.where(Task.id != exclude_task_id)

        candidates = list((await db.execute(stmt.limit(25))).scalars().all())
        tokens = RagService._tokenize(query_text)

        ranked: list[tuple[int, Task]] = []
        for candidate in candidates:
            haystack = f"{candidate.title} {candidate.content} {' '.join(candidate.tags)}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                ranked.append((score, candidate))

        ranked.sort(key=lambda item: (-item[0], item[1].created_at), reverse=False)
        return [
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status.value,
                "score": score,
            }
            for score, task in ranked[:limit]
        ]

    @staticmethod
    async def index_task_context(
        task: Task,
        attachments: list[TaskAttachment],
        *,
        validation_result: dict | None = None,
    ) -> list[str]:
        chunk_ids = await run_rag_pipeline(
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
        task.indexed_at = datetime.now(timezone.utc)
        return chunk_ids
