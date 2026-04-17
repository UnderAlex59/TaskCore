from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.validation_graph import run_validation_graph
from app.models.message import Message, MessageType
from app.models.project import ProjectMember
from app.models.task import Task, TaskAttachment, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import (
    TaskApprove,
    TaskAttachmentRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    ValidationIssue,
    ValidationResult,
)
from app.services.audit_service import AuditService
from app.services.project_service import ProjectService
from app.services.rag_service import RagService


class TaskService:
    editable_statuses = {TaskStatus.DRAFT, TaskStatus.NEEDS_REWORK}
    approval_roles = {UserRole.ADMIN, UserRole.ANALYST}
    team_chat_statuses = {TaskStatus.READY_FOR_DEV, TaskStatus.IN_PROGRESS, TaskStatus.DONE}

    @staticmethod
    async def get_task_or_404(project_id: str, task_id: str, db: AsyncSession) -> Task:
        task = await db.get(Task, task_id)
        if task is None or task.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена",
            )
        return task

    @staticmethod
    async def get_task_with_access(task_id: str, current_user: User, db: AsyncSession) -> Task:
        task = await db.get(Task, task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена",
            )

        await ProjectService.ensure_project_access(task.project_id, current_user, db)
        return task

    @staticmethod
    async def get_task_with_chat_access(task_id: str, current_user: User, db: AsyncSession) -> Task:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if TaskService.can_access_chat(task, current_user):
            return task

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к чату этой задачи",
        )

    @staticmethod
    def can_access_chat(task: Task, current_user: User) -> bool:
        if current_user.role == UserRole.ADMIN:
            return True
        if current_user.id == task.analyst_id:
            return True
        if task.status in TaskService.team_chat_statuses:
            return current_user.id in {task.developer_id, task.tester_id}
        return False

    @staticmethod
    async def _get_attachments(task_id: str, db: AsyncSession) -> list[TaskAttachment]:
        stmt: Select[tuple[TaskAttachment]] = (
            select(TaskAttachment)
            .where(TaskAttachment.task_id == task_id)
            .order_by(TaskAttachment.created_at.asc())
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def _get_project_member_or_422(
        project_id: str,
        user_id: str,
        expected_role: UserRole,
        db: AsyncSession,
    ) -> ProjectMember:
        membership = await ProjectService.get_membership(project_id, user_id, db)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Участник команды должен состоять в проекте",
            )
        if membership.role != expected_role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Участник должен иметь роль {expected_role.value} в проекте",
            )
        return membership

    @staticmethod
    async def _get_user_name(user_id: str, db: AsyncSession) -> str:
        user = await db.get(User, user_id)
        if user is None:
            return user_id
        return user.full_name

    @staticmethod
    def _serialize_task(task: Task, attachments: list[TaskAttachment]) -> TaskRead:
        return TaskRead(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            content=task.content,
            tags=task.tags,
            status=task.status,
            created_by=task.created_by,
            analyst_id=task.analyst_id,
            developer_id=task.developer_id,
            tester_id=task.tester_id,
            validation_result=task.validation_result,
            attachments=[TaskAttachmentRead.model_validate(item) for item in attachments],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    async def list_tasks(
        project_id: str,
        current_user: User,
        db: AsyncSession,
        *,
        status_filter: TaskStatus | None = None,
        tags: list[str] | None = None,
        analyst_id: str | None = None,
        developer_id: str | None = None,
        tester_id: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> list[TaskRead]:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        stmt: Select[tuple[Task]] = select(Task).where(Task.project_id == project_id)

        if status_filter is not None:
            stmt = stmt.where(Task.status == status_filter)
        if tags:
            stmt = stmt.where(Task.tags.overlap(tags))
        if analyst_id:
            stmt = stmt.where(Task.analyst_id == analyst_id)
        if developer_id:
            stmt = stmt.where(Task.developer_id == developer_id)
        if tester_id:
            stmt = stmt.where(Task.tester_id == tester_id)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Task.title.ilike(pattern), Task.content.ilike(pattern)))

        offset = max(page - 1, 0) * size
        tasks = list(
            (
                await db.execute(
                    stmt.order_by(Task.updated_at.desc(), Task.created_at.desc())
                    .offset(offset)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        attachments_map = {
            task.id: await TaskService._get_attachments(task.id, db) for task in tasks
        }
        return [TaskService._serialize_task(task, attachments_map.get(task.id, [])) for task in tasks]

    @staticmethod
    async def create_task(
        project_id: str,
        payload: TaskCreate,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.approval_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут создавать задачи",
            )

        task = Task(
            project_id=project_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
            created_by=current_user.id,
            analyst_id=current_user.id,
        )
        db.add(task)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.created",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
        )
        await db.commit()
        await db.refresh(task)
        return TaskService._serialize_task(task, [])

    @staticmethod
    async def get_task(project_id: str, task_id: str, current_user: User, db: AsyncSession) -> TaskRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        task = await TaskService.get_task_or_404(project_id, task_id, db)
        attachments = await TaskService._get_attachments(task.id, db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def update_task(
        project_id: str,
        task_id: str,
        payload: TaskUpdate,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.approval_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут редактировать задачи",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        if task.status not in TaskService.editable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Задачу можно редактировать только в статусе черновика или доработки",
            )

        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field_name, value)

        task.validation_result = None
        attachments = await TaskService._get_attachments(task.id, db)
        await RagService.index_task_context(task, attachments, validation_result=None)
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.updated",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
        )
        await db.commit()
        await db.refresh(task)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def approve_task(
        task_id: str,
        payload: TaskApprove,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.role not in TaskService.approval_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут подтверждать задачу",
            )
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Задачу можно подтвердить только после успешного ревью",
            )
        if payload.developer_id == payload.tester_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Разработчик и тестировщик должны быть разными пользователями",
            )

        await TaskService._get_project_member_or_422(task.project_id, payload.developer_id, UserRole.DEVELOPER, db)
        await TaskService._get_project_member_or_422(task.project_id, payload.tester_id, UserRole.TESTER, db)

        task.developer_id = payload.developer_id
        task.tester_id = payload.tester_id
        task.status = TaskStatus.READY_FOR_DEV

        developer_name = await TaskService._get_user_name(payload.developer_id, db)
        tester_name = await TaskService._get_user_name(payload.tester_id, db)
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=(
                    "Команда задачи сформирована. "
                    f"Разработчик: {developer_name}. "
                    f"Тестировщик: {tester_name}. "
                    "Командный чат открыт."
                ),
                source_ref={
                    "collection": "tasks",
                    "developer_id": payload.developer_id,
                    "tester_id": payload.tester_id,
                },
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.approved",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={
                "developer_id": payload.developer_id,
                "tester_id": payload.tester_id,
            },
        )

        attachments = await TaskService._get_attachments(task.id, db)
        await db.commit()
        await db.refresh(task)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def delete_task(project_id: str, task_id: str, current_user: User, db: AsyncSession) -> None:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.approval_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут удалять задачи",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.deleted",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
        )
        await db.delete(task)
        await db.commit()

    @staticmethod
    async def upload_attachment(
        project_id: str,
        task_id: str,
        file: UploadFile,
        current_user: User,
        db: AsyncSession,
        upload_dir: str,
    ) -> TaskAttachmentRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        task = await TaskService.get_task_or_404(project_id, task_id, db)

        original_name = file.filename or "attachment"
        safe_stem = re.sub(r"[^\w.-]+", "_", Path(original_name).stem).strip("._") or "attachment"
        suffix = Path(original_name).suffix
        target_dir = Path(upload_dir) / project_id / task.id
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{safe_stem}{suffix}"
        target_path = target_dir / stored_name
        content = await file.read()
        target_path.write_bytes(content)

        attachment = TaskAttachment(
            task_id=task.id,
            filename=original_name,
            content_type=file.content_type or "application/octet-stream",
            storage_path=str(target_path),
            alt_text=f"Загруженный файл: {original_name}",
        )
        db.add(attachment)
        await db.flush()

        attachments = await TaskService._get_attachments(task.id, db)
        await RagService.index_task_context(
            task,
            attachments,
            validation_result=task.validation_result,
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.attachment_uploaded",
            entity_type="task_attachment",
            entity_id=attachment.id,
            project_id=project_id,
            task_id=task.id,
            metadata={"filename": original_name},
        )
        await db.commit()
        await db.refresh(attachment)
        return TaskAttachmentRead.model_validate(attachment)

    @staticmethod
    async def validate_task(task_id: str, current_user: User, db: AsyncSession) -> ValidationResult:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.role not in TaskService.approval_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут запускать проверку задач",
            )
        if task.status not in TaskService.editable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Перед проверкой задача должна быть в статусе черновика или доработки",
            )

        task.status = TaskStatus.VALIDATING
        await db.flush()

        rules = await ProjectService.get_active_rules(task.project_id, task.tags, db)
        attachments = await TaskService._get_attachments(task.id, db)
        related_tasks = await RagService.search_related_tasks(
            db,
            project_id=task.project_id,
            query_text=f"{task.title}\n{task.content}",
            exclude_task_id=task.id,
            limit=3,
        )

        validation_state = await run_validation_graph(
            title=task.title,
            content=task.content,
            tags=task.tags,
            custom_rules=[
                {
                    "title": rule.title,
                    "description": rule.description,
                    "applies_to_tags": rule.applies_to_tags,
                }
                for rule in rules
            ],
            related_tasks=related_tasks,
            attachment_names=[item.filename for item in attachments],
        )
        validation_result = ValidationResult(
            verdict=str(validation_state["verdict"]),
            issues=[
                ValidationIssue.model_validate(item)
                for item in validation_state.get("issues", [])
            ],
            questions=list(validation_state.get("questions", [])),
            validated_at=datetime.now(timezone.utc),
        )

        task.validation_result = validation_result.model_dump(mode="json")
        task.status = (
            TaskStatus.AWAITING_APPROVAL
            if validation_result.verdict == "approved"
            else TaskStatus.NEEDS_REWORK
        )

        chunk_ids = await RagService.index_task_context(
            task,
            attachments,
            validation_result=task.validation_result,
        )
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="QAAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=TaskService._format_validation_message(validation_result),
                source_ref={
                    "task_id": task.id,
                    "chunk_ids": chunk_ids,
                    "related_task_ids": [
                        item["task_id"] for item in related_tasks if "task_id" in item
                    ],
                    "collection": "tasks",
                },
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.validated",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={"verdict": validation_result.verdict},
        )
        await db.commit()
        return validation_result

    @staticmethod
    def _format_validation_message(result: ValidationResult) -> str:
        if result.verdict == "approved":
            if result.questions:
                return (
                    "Требование прошло автоматическую проверку. Остались уточняющие "
                    "вопросы: " + "; ".join(result.questions)
                )
            return "Требование прошло автоматическую проверку и ожидает подтверждения."

        issue_text = "; ".join(issue.message for issue in result.issues)
        if result.questions:
            return f"Найдены проблемы: {issue_text}. Нужно уточнить: {'; '.join(result.questions)}"
        return f"Найдены проблемы: {issue_text}"
