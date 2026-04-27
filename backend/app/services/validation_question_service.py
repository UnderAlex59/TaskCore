from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task, TaskAttachment, TaskStatus
from app.models.user import User
from app.models.validation_question import ValidationQuestion
from app.schemas.admin_validation import ValidationQuestionPageRead, ValidationQuestionRead
from app.services.audit_service import AuditService
from app.services.qdrant_service import QdrantService
from app.services.rag_service import RagService

ValidationVerdict = Literal["approved", "needs_rework"]


class ValidationQuestionService:
    @staticmethod
    def _parse_validated_at(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    @staticmethod
    async def clear_for_task(task_id: str, db: AsyncSession) -> None:
        await db.execute(delete(ValidationQuestion).where(ValidationQuestion.task_id == task_id))
        await QdrantService.delete_project_questions_for_task(task_id=task_id)

    @staticmethod
    def _normalize_question_text(question_text: str) -> str:
        normalized = question_text.strip()
        if not normalized:
            return ""
        return normalized[0].upper() + normalized[1:]

    @staticmethod
    async def _sync_project_questions_index(task: Task, db: AsyncSession) -> None:
        rows = list(
            (
                await db.execute(
                    select(ValidationQuestion)
                    .where(ValidationQuestion.task_id == task.id)
                    .where(ValidationQuestion.source == "chat")
                    .order_by(
                        ValidationQuestion.sort_order.asc(),
                        ValidationQuestion.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        await QdrantService.replace_project_questions(
            task_id=task.id,
            project_id=task.project_id,
            tags=list(task.tags),
            questions=[
                {
                    "question_id": row.id,
                    "question_text": row.question_text,
                    "validation_verdict": row.validation_verdict,
                }
                for row in rows
            ],
        )

    @staticmethod
    async def sync_project_questions_index(task: Task, db: AsyncSession) -> None:
        await ValidationQuestionService._sync_project_questions_index(task, db)

    @staticmethod
    async def _sync_task_context_index(
        task: Task,
        db: AsyncSession,
        *,
        actor_user_id: str | None,
    ) -> None:
        attachments = list(
            (
                await db.execute(
                    select(TaskAttachment)
                    .where(TaskAttachment.task_id == task.id)
                    .order_by(TaskAttachment.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=actor_user_id,
            validation_result=task.validation_result,
        )

    @staticmethod
    async def record_chat_question(
        task: Task,
        question_text: str,
        db: AsyncSession,
        *,
        actor_user_id: str | None = None,
    ) -> ValidationQuestion | None:
        normalized_question = ValidationQuestionService._normalize_question_text(question_text)
        if not normalized_question:
            return None

        existing = (
            await db.execute(
                select(ValidationQuestion).where(
                    ValidationQuestion.task_id == task.id,
                    ValidationQuestion.question_text == normalized_question,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        validation_result = dict(task.validation_result or {})
        verdict = str(validation_result.get("verdict", "needs_rework"))
        sort_order = int(
            (
                await db.execute(
                    select(func.max(ValidationQuestion.sort_order)).where(
                        ValidationQuestion.task_id == task.id
                    )
                )
            ).scalar_one_or_none()
            or -1
        ) + 1

        task_context_updated = False
        if validation_result:
            current_questions = [
                ValidationQuestionService._normalize_question_text(str(item))
                for item in list(validation_result.get("questions", []))
            ]
            if normalized_question not in current_questions:
                validation_result["questions"] = [
                    question for question in current_questions if question
                ] + [normalized_question]
                task.validation_result = validation_result
                task_context_updated = True

        question = ValidationQuestion(
            task_id=task.id,
            source="chat",
            question_text=normalized_question,
            validation_verdict=verdict,
            validated_at=None,
            sort_order=sort_order,
        )
        db.add(question)
        await db.flush()
        await ValidationQuestionService._sync_project_questions_index(task, db)
        if task_context_updated:
            await ValidationQuestionService._sync_task_context_index(
                task,
                db,
                actor_user_id=actor_user_id,
            )
        return question

    @staticmethod
    async def list_questions(
        db: AsyncSession,
        *,
        project_id: str | None = None,
        task_status: TaskStatus | None = None,
        verdict: ValidationVerdict | None = None,
        tag: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> ValidationQuestionPageRead:
        stmt: Select[tuple[ValidationQuestion, Task, Project]] = (
            select(ValidationQuestion, Task, Project)
            .join(Task, Task.id == ValidationQuestion.task_id)
            .join(Project, Project.id == Task.project_id)
            .where(ValidationQuestion.source == "chat")
        )

        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if task_status is not None:
            stmt = stmt.where(Task.status == task_status)
        if verdict is not None:
            stmt = stmt.where(ValidationQuestion.validation_verdict == verdict)
        if tag:
            stmt = stmt.where(Task.tags.overlap([tag]))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Task.title.ilike(pattern),
                    ValidationQuestion.question_text.ilike(pattern),
                )
            )

        total = int(
            (
                await db.execute(
                    select(func.count()).select_from(stmt.order_by(None).subquery())
                )
            ).scalar_one()
        )

        offset = max(page - 1, 0) * size
        rows = (
            await db.execute(
                stmt.order_by(
                    ValidationQuestion.validated_at.desc().nullslast(),
                    ValidationQuestion.created_at.desc(),
                    ValidationQuestion.sort_order.asc(),
                )
                .offset(offset)
                .limit(size)
            )
        ).all()

        return ValidationQuestionPageRead(
            page=page,
            page_size=size,
            total=total,
            items=[
                ValidationQuestionRead(
                    id=question.id,
                    task_id=task.id,
                    project_id=project.id,
                    project_name=project.name,
                    task_title=task.title,
                    task_status=task.status,
                    tags=list(task.tags),
                    question_text=question.question_text,
                    validation_verdict=question.validation_verdict,
                    validated_at=question.validated_at,
                    created_at=question.created_at,
                    updated_at=question.updated_at,
                )
                for question, task, project in rows
            ],
        )

    @staticmethod
    async def delete_question(question_id: str, current_user: User, db: AsyncSession) -> None:
        row = (
            await db.execute(
                select(ValidationQuestion, Task)
                .join(Task, Task.id == ValidationQuestion.task_id)
                .where(ValidationQuestion.id == question_id)
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Вопрос валидации не найден",
            )

        question, task = row
        validation_result = dict(task.validation_result or {})
        current_questions = list(validation_result.get("questions", []))
        updated_questions: list[str] = []
        removed = False
        for item in current_questions:
            if not removed and item == question.question_text:
                removed = True
                continue
            updated_questions.append(item)

        if validation_result:
            validation_result["questions"] = updated_questions
            task.validation_result = validation_result

        await db.delete(question)
        await db.flush()
        await ValidationQuestionService._sync_project_questions_index(task, db)
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="admin.validation_question.deleted",
            entity_type="validation_question",
            entity_id=question.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={"question_text": question.question_text},
        )
        await db.commit()
