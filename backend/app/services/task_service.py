from __future__ import annotations

import mimetypes
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Select, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.task_tag_suggestion_graph import run_task_tag_suggestion_graph
from app.agents.validation_graph import run_validation_graph
from app.models.audit_event import AuditEvent
from app.models.llm_request_log import LLMRequestLog
from app.models.message import Message, MessageType
from app.models.project import ProjectMember
from app.models.task import Task, TaskAttachment, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import (
    TaskApprove,
    TaskAttachmentRead,
    TaskCreate,
    TaskRead,
    TaskTagSuggestionRequest,
    TaskTagSuggestionResponse,
    TaskUpdate,
    ValidationIssue,
    ValidationResult,
)
from app.services.audit_service import AuditService
from app.services.chat_realtime import chat_connection_manager, serialize_message
from app.services.project_service import ProjectService
from app.services.qdrant_service import QdrantService
from app.services.rag_service import RagService
from app.services.task_tag_service import TaskTagService
from app.services.validation_question_service import ValidationQuestionService


class TaskService:
    revalidation_flag = "requires_revalidation"
    pre_approval_editable_statuses = {
        TaskStatus.DRAFT,
        TaskStatus.NEEDS_REWORK,
        TaskStatus.AWAITING_APPROVAL,
    }
    post_approval_editable_statuses = {
        TaskStatus.READY_FOR_DEV,
        TaskStatus.IN_PROGRESS,
        TaskStatus.READY_FOR_TESTING,
        TaskStatus.TESTING,
        TaskStatus.DONE,
    }
    editable_statuses = pre_approval_editable_statuses | post_approval_editable_statuses
    validation_roles = {UserRole.ADMIN, UserRole.ANALYST}
    review_roles = {UserRole.ADMIN, UserRole.ANALYST, UserRole.MANAGER}
    team_chat_statuses = {
        TaskStatus.READY_FOR_DEV,
        TaskStatus.IN_PROGRESS,
        TaskStatus.READY_FOR_TESTING,
        TaskStatus.TESTING,
        TaskStatus.DONE,
    }

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
        if current_user.id == task.reviewer_analyst_id:
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
    async def _get_attachment_or_404(
        task_id: str,
        attachment_id: str,
        db: AsyncSession,
    ) -> TaskAttachment:
        attachment = await db.get(TaskAttachment, attachment_id)
        if attachment is None or attachment.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Вложение не найдено",
            )
        return attachment

    @staticmethod
    def _attachment_path_or_404(attachment: TaskAttachment, upload_dir: str) -> Path:
        path = Path(attachment.storage_path)
        try:
            path.resolve().relative_to(Path(upload_dir).resolve())
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Файл вложения не найден",
            ) from error
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Файл вложения не найден",
            )
        return path

    @staticmethod
    def _delete_attachment_file(path: Path, upload_dir: str) -> None:
        try:
            path.resolve().relative_to(Path(upload_dir).resolve())
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _resolve_content_type(filename: str, uploaded_content_type: str | None) -> str:
        if uploaded_content_type and uploaded_content_type != "application/octet-stream":
            return uploaded_content_type
        guessed_content_type, _ = mimetypes.guess_type(filename)
        return guessed_content_type or uploaded_content_type or "application/octet-stream"

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
    async def _broadcast_latest_agent_message(
        task_id: str,
        agent_name: str,
        db: AsyncSession,
    ) -> None:
        message = (
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.task_id == task_id,
                        Message.author_id.is_(None),
                        Message.agent_name == agent_name,
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if message is None:
            return
        await chat_connection_manager.broadcast_messages(
            task_id,
            [
                serialize_message(
                    message,
                    author_name=None,
                    author_avatar_url=None,
                )
            ],
        )

    @staticmethod
    def _can_configure_review(task: Task, current_user: User) -> bool:
        return current_user.role in {UserRole.ADMIN, UserRole.MANAGER} or current_user.id == task.analyst_id

    @staticmethod
    def _is_secondary_reviewer(task: Task, current_user: User) -> bool:
        return task.reviewer_analyst_id is not None and current_user.id == task.reviewer_analyst_id

    @staticmethod
    def _has_stale_embeddings(task: Task) -> bool:
        if task.indexed_at is None:
            return True
        if task.updated_at is None:
            return False
        return task.updated_at > task.indexed_at

    @staticmethod
    def _requires_revalidation(task: Task) -> bool:
        return bool(
            isinstance(task.validation_result, dict)
            and task.validation_result.get(TaskService.revalidation_flag) is True
        )

    @staticmethod
    def _ensure_index_is_synced(task: Task, *, detail: str) -> None:
        if TaskService._has_stale_embeddings(task):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail,
            )

    @staticmethod
    def _mark_requires_revalidation(task: Task) -> None:
        validation_result = dict(task.validation_result or {})
        validation_result[TaskService.revalidation_flag] = True
        task.validation_result = validation_result

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
            reviewer_analyst_id=task.reviewer_analyst_id,
            developer_id=task.developer_id,
            tester_id=task.tester_id,
            reviewer_approved_at=task.reviewer_approved_at,
            validation_result=task.validation_result,
            attachments=[TaskAttachmentRead.model_validate(item) for item in attachments],
            indexed_at=task.indexed_at,
            embeddings_stale=TaskService._has_stale_embeddings(task),
            requires_revalidation=TaskService._requires_revalidation(task),
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
        return [
            TaskService._serialize_task(task, attachments_map.get(task.id, [])) for task in tasks
        ]

    @staticmethod
    async def create_task(
        project_id: str,
        payload: TaskCreate,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут создавать задачи",
            )

        task = Task(
            project_id=project_id,
            title=payload.title,
            content=payload.content,
            tags=await TaskTagService.validate_reference_tags(project_id, payload.tags, db),
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
    async def get_task(
        project_id: str,
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
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
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут редактировать задачи",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        if task.status not in TaskService.editable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Задачу нельзя редактировать во время автоматической проверки",
            )

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            attachments = await TaskService._get_attachments(task.id, db)
            return TaskService._serialize_task(task, attachments)

        if "tags" in updates:
            updates["tags"] = await TaskTagService.validate_reference_tags(
                project_id,
                list(updates["tags"] or []),
                db,
            )

        status_before_update = task.status
        for field_name, value in updates.items():
            setattr(task, field_name, value)

        update_timestamp = datetime.now(UTC)
        task.updated_at = update_timestamp
        attachments = await TaskService._get_attachments(task.id, db)
        audit_metadata: dict[str, bool | str] = {}

        if status_before_update in TaskService.pre_approval_editable_statuses:
            task.validation_result = None
            if status_before_update == TaskStatus.AWAITING_APPROVAL:
                task.status = TaskStatus.NEEDS_REWORK
            await ValidationQuestionService.clear_for_task(task.id, db)
            await RagService.index_task_context(
                db,
                task,
                attachments,
                actor_user_id=current_user.id,
                validation_result=None,
            )
            audit_metadata["embeddings_reindexed"] = task.indexed_at is not None
        else:
            TaskService._mark_requires_revalidation(task)
            audit_metadata["embeddings_reindexed"] = False
            audit_metadata["commit_required"] = True
            audit_metadata["requires_revalidation"] = True

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.updated",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
            metadata=audit_metadata,
        )
        await db.commit()
        await db.refresh(task)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def commit_task_changes(
        project_id: str,
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут коммитить изменения задачи",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        if task.status not in TaskService.editable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя коммитить изменения задачи во время автоматической проверки",
            )

        attachments = await TaskService._get_attachments(task.id, db)
        stale_before_commit = TaskService._has_stale_embeddings(task)
        current_timestamp = datetime.now(UTC)
        task.updated_at = current_timestamp
        await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
            validation_result=task.validation_result,
        )
        TaskService._ensure_index_is_synced(
            task,
            detail=(
                "Не удалось опубликовать изменения в семантический индекс. "
                "Commit не был сохранен."
            ),
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.changes_committed",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            task_id=task.id,
            metadata={"embeddings_were_stale": stale_before_commit},
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
        if current_user.role not in TaskService.review_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики, менеджеры и администраторы могут подтверждать задачу",
            )
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Задачу можно подтвердить только после успешного ревью",
            )
        can_configure_review = TaskService._can_configure_review(task, current_user)
        is_secondary_reviewer = TaskService._is_secondary_reviewer(task, current_user)
        if not can_configure_review and not is_secondary_reviewer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Подтвердить задачу может аналитик задачи, менеджер или назначенный второй аналитик",
            )

        current_timestamp = datetime.now(UTC)
        payload_data = payload.model_dump(exclude_unset=True)
        reviewer_assignment_changed = False
        team_assignment_changed = False
        reviewer_confirmed = False

        if can_configure_review:
            if "reviewer_analyst_id" in payload_data:
                reviewer_analyst_id = payload_data["reviewer_analyst_id"]
                if reviewer_analyst_id == task.analyst_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Второй аналитик должен отличаться от основного аналитика задачи",
                    )
                if reviewer_analyst_id is not None:
                    await TaskService._get_project_member_or_422(
                        task.project_id,
                        reviewer_analyst_id,
                        UserRole.ANALYST,
                        db,
                    )
                if reviewer_analyst_id != task.reviewer_analyst_id:
                    task.reviewer_analyst_id = reviewer_analyst_id
                    task.reviewer_approved_at = None
                    reviewer_assignment_changed = True

            if "developer_id" in payload_data and payload_data["developer_id"] is not None:
                await TaskService._get_project_member_or_422(
                    task.project_id,
                    payload_data["developer_id"],
                    UserRole.DEVELOPER,
                    db,
                )
                if payload_data["developer_id"] != task.developer_id:
                    task.developer_id = payload_data["developer_id"]
                    team_assignment_changed = True

            if "tester_id" in payload_data and payload_data["tester_id"] is not None:
                await TaskService._get_project_member_or_422(
                    task.project_id,
                    payload_data["tester_id"],
                    UserRole.TESTER,
                    db,
                )
                if payload_data["tester_id"] != task.tester_id:
                    task.tester_id = payload_data["tester_id"]
                    team_assignment_changed = True

        if task.developer_id is not None and task.developer_id == task.tester_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Разработчик и тестировщик должны быть разными пользователями",
            )

        if is_secondary_reviewer and task.reviewer_analyst_id is not None and task.reviewer_approved_at is None:
            task.reviewer_approved_at = current_timestamp
            reviewer_confirmed = True

        waiting_for_second_review = (
            task.reviewer_analyst_id is not None and task.reviewer_approved_at is None
        )
        if not waiting_for_second_review and (task.developer_id is None or task.tester_id is None):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Перед переводом задачи в разработку нужно назначить разработчика и тестировщика",
            )

        task.updated_at = current_timestamp
        attachments = await TaskService._get_attachments(task.id, db)
        approval_message: Message | None = None

        if waiting_for_second_review:
            reviewer_name = await TaskService._get_user_name(task.reviewer_analyst_id, db)
            if reviewer_assignment_changed or team_assignment_changed:
                approval_message = Message(
                    task_id=task.id,
                    author_id=None,
                    agent_name="ManagerAgent",
                    message_type=MessageType.AGENT_ANSWER,
                    content=(
                        "Задача ожидает второе аналитическое ревью. "
                        f"Второй аналитик: {reviewer_name}. "
                        "После его подтверждения задача перейдет в статус готово к разработке."
                    ),
                    source_ref={
                        "collection": "tasks",
                        "reviewer_analyst_id": task.reviewer_analyst_id,
                    },
                )
                db.add(approval_message)
            AuditService.record(
                db,
                actor_user_id=current_user.id,
                event_type="task.review_configured",
                entity_type="task",
                entity_id=task.id,
                project_id=task.project_id,
                task_id=task.id,
                metadata={
                    "developer_id": task.developer_id,
                    "tester_id": task.tester_id,
                    "reviewer_analyst_id": task.reviewer_analyst_id,
                },
            )
        else:
            task.status = TaskStatus.READY_FOR_DEV
            developer_name = await TaskService._get_user_name(task.developer_id, db)
            tester_name = await TaskService._get_user_name(task.tester_id, db)
            approval_message = Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=(
                    "Команда задачи сформирована. "
                    f"Разработчик: {developer_name}. "
                    f"Тестировщик: {tester_name}. "
                    + (
                        "Второе аналитическое ревью подтверждено. "
                        if task.reviewer_analyst_id is not None
                        else ""
                    )
                    + "Командный чат открыт."
                ),
                source_ref={
                    "collection": "tasks",
                    "developer_id": task.developer_id,
                    "tester_id": task.tester_id,
                    "reviewer_analyst_id": task.reviewer_analyst_id,
                },
            )
            db.add(approval_message)
            AuditService.record(
                db,
                actor_user_id=current_user.id,
                event_type="task.approved",
                entity_type="task",
                entity_id=task.id,
                project_id=task.project_id,
                task_id=task.id,
                metadata={
                    "developer_id": task.developer_id,
                    "tester_id": task.tester_id,
                    "reviewer_analyst_id": task.reviewer_analyst_id,
                    "reviewer_confirmed": reviewer_confirmed or task.reviewer_approved_at is not None,
                },
            )
            await RagService.index_task_context(
                db,
                task,
                attachments,
                actor_user_id=current_user.id,
                validation_result=task.validation_result,
            )

        await db.commit()
        await db.refresh(task)
        if approval_message is not None:
            await TaskService._broadcast_latest_agent_message(task.id, "ManagerAgent", db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def start_development(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.id != task.developer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только назначенный разработчик может взять задачу в разработку",
            )
        if task.status != TaskStatus.READY_FOR_DEV:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Задачу можно взять в разработку только из статуса готово к разработке",
            )

        task.status = TaskStatus.IN_PROGRESS
        task.updated_at = datetime.now(UTC)
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=f"Разработчик {current_user.full_name} взял задачу в работу.",
                source_ref={"collection": "tasks", "status": task.status.value},
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.development_started",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
        )
        attachments = await TaskService._get_attachments(task.id, db)
        await db.commit()
        await db.refresh(task)
        await TaskService._broadcast_latest_agent_message(task.id, "ManagerAgent", db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def mark_ready_for_testing(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.id != task.developer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только назначенный разработчик может перевести задачу в статус готово к тестированию",
            )
        if task.status != TaskStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Перевести задачу в статус готово к тестированию можно только из разработки",
            )

        task.status = TaskStatus.READY_FOR_TESTING
        task.updated_at = datetime.now(UTC)
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=f"Разработчик {current_user.full_name} перевел задачу в статус готово к тестированию.",
                source_ref={"collection": "tasks", "status": task.status.value},
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.ready_for_testing",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
        )
        attachments = await TaskService._get_attachments(task.id, db)
        await db.commit()
        await db.refresh(task)
        await TaskService._broadcast_latest_agent_message(task.id, "ManagerAgent", db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def start_testing(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.id != task.tester_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только назначенный тестировщик может взять задачу в тестирование",
            )
        if task.status != TaskStatus.READY_FOR_TESTING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Взять задачу в тестирование можно только из статуса готово к тестированию",
            )

        task.status = TaskStatus.TESTING
        task.updated_at = datetime.now(UTC)
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=f"Тестировщик {current_user.full_name} начал тестирование задачи.",
                source_ref={"collection": "tasks", "status": task.status.value},
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.testing_started",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
        )
        attachments = await TaskService._get_attachments(task.id, db)
        await db.commit()
        await db.refresh(task)
        await TaskService._broadcast_latest_agent_message(task.id, "ManagerAgent", db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def complete_task(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> TaskRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.id != task.tester_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только назначенный тестировщик может завершить задачу",
            )
        if task.status != TaskStatus.TESTING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Завершить задачу можно только после начала тестирования",
            )

        task.status = TaskStatus.DONE
        task.updated_at = datetime.now(UTC)
        db.add(
            Message(
                task_id=task.id,
                author_id=None,
                agent_name="ManagerAgent",
                message_type=MessageType.AGENT_ANSWER,
                content=f"Тестировщик {current_user.full_name} завершил тестирование. Задача выполнена.",
                source_ref={"collection": "tasks", "status": task.status.value},
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.completed",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
        )
        attachments = await TaskService._get_attachments(task.id, db)
        await db.commit()
        await db.refresh(task)
        await TaskService._broadcast_latest_agent_message(task.id, "ManagerAgent", db)
        return TaskService._serialize_task(task, attachments)

    @staticmethod
    async def delete_task(
        project_id: str,
        task_id: str,
        current_user: User,
        db: AsyncSession,
        upload_dir: str | None = None,
    ) -> None:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут удалять задачи",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        attachments = await TaskService._get_attachments(task.id, db)
        attachment_paths = [Path(attachment.storage_path) for attachment in attachments]
        await db.execute(
            update(AuditEvent)
            .where(AuditEvent.task_id == task.id)
            .values(task_id=None)
        )
        await db.execute(
            update(LLMRequestLog)
            .where(LLMRequestLog.task_id == task.id)
            .values(task_id=None)
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.deleted",
            entity_type="task",
            entity_id=task.id,
            project_id=project_id,
            metadata={"task_id": task.id, "attachment_count": len(attachments)},
        )
        await db.delete(task)
        await db.commit()
        await QdrantService.delete_task_artifacts(task_id=task.id)
        if upload_dir is not None:
            for path in attachment_paths:
                TaskService._delete_attachment_file(path, upload_dir)

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
            content_type=TaskService._resolve_content_type(original_name, file.content_type),
            storage_path=str(target_path),
            alt_text=None,
        )
        db.add(attachment)
        await db.flush()

        attachments = await TaskService._get_attachments(task.id, db)
        current_timestamp = datetime.now(UTC)
        task.updated_at = current_timestamp
        if task.status in TaskService.post_approval_editable_statuses:
            TaskService._mark_requires_revalidation(task)
        await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
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
    async def get_attachment_file(
        project_id: str,
        task_id: str,
        attachment_id: str,
        current_user: User,
        db: AsyncSession,
        upload_dir: str,
    ) -> tuple[TaskAttachment, Path]:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        task = await TaskService.get_task_or_404(project_id, task_id, db)
        attachment = await TaskService._get_attachment_or_404(task.id, attachment_id, db)
        return attachment, TaskService._attachment_path_or_404(attachment, upload_dir)

    @staticmethod
    async def delete_attachment(
        project_id: str,
        task_id: str,
        attachment_id: str,
        current_user: User,
        db: AsyncSession,
        upload_dir: str,
    ) -> None:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        task = await TaskService.get_task_or_404(project_id, task_id, db)
        attachment = await TaskService._get_attachment_or_404(task.id, attachment_id, db)
        path = Path(attachment.storage_path)

        await db.delete(attachment)
        await db.flush()

        attachments = await TaskService._get_attachments(task.id, db)
        current_timestamp = datetime.now(UTC)
        task.updated_at = current_timestamp
        if task.status in TaskService.post_approval_editable_statuses:
            TaskService._mark_requires_revalidation(task)
        await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
            validation_result=task.validation_result,
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="task.attachment_deleted",
            entity_type="task_attachment",
            entity_id=attachment.id,
            project_id=project_id,
            task_id=task.id,
            metadata={"filename": attachment.filename},
        )
        await db.commit()

        TaskService._delete_attachment_file(path, upload_dir)

    @staticmethod
    async def validate_task(task_id: str, current_user: User, db: AsyncSession) -> ValidationResult:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут запускать проверку задач",
            )
        is_initial_validation = task.status in {TaskStatus.DRAFT, TaskStatus.NEEDS_REWORK}
        is_post_approval_revalidation = (
            task.status in TaskService.post_approval_editable_statuses
            and TaskService._requires_revalidation(task)
        )
        if is_post_approval_revalidation and TaskService._has_stale_embeddings(task):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Перед повторной проверкой нужно выполнить commit "
                    "и пересчитать эмбеддинги задачи"
                ),
            )
        if not is_initial_validation and not is_post_approval_revalidation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Перед проверкой задача должна быть в статусе черновика или доработки",
            )

        status_before_validation = task.status
        task.status = TaskStatus.VALIDATING
        await db.flush()

        project = await ProjectService.get_project_or_404(task.project_id, db)
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
            db=db,
            actor_user_id=current_user.id,
            task_id=task.id,
            project_id=task.project_id,
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
            validation_node_settings=project.validation_node_settings,
        )
        validation_result = ValidationResult(
            verdict=str(validation_state["verdict"]),
            issues=[
                ValidationIssue.model_validate(item) for item in validation_state.get("issues", [])
            ],
            questions=list(validation_state.get("questions", [])),
            validated_at=datetime.now(UTC),
        )

        task.validation_result = validation_result.model_dump(mode="json")
        if is_post_approval_revalidation and validation_result.verdict == "approved":
            task.status = status_before_validation
        else:
            task.status = (
                TaskStatus.AWAITING_APPROVAL
                if validation_result.verdict == "approved"
                else TaskStatus.NEEDS_REWORK
            )
        current_timestamp = datetime.now(UTC)
        task.updated_at = current_timestamp
        chunk_ids = await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
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
                    "collection": "task_knowledge" if chunk_ids else "tasks",
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
            metadata={
                "verdict": validation_result.verdict,
                "post_approval_revalidation": is_post_approval_revalidation,
            },
        )
        await db.commit()
        validation_message = (
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.task_id == task.id,
                        Message.author_id.is_(None),
                        Message.agent_name == "QAAgent",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if validation_message is not None:
            await chat_connection_manager.broadcast_messages(
                task.id,
                [
                    serialize_message(
                        validation_message,
                        author_name=None,
                        author_avatar_url=None,
                    )
                ],
            )
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
    @staticmethod
    async def suggest_task_tags(
        project_id: str,
        task_id: str,
        payload: TaskTagSuggestionRequest,
        current_user: User,
        db: AsyncSession,
    ) -> TaskTagSuggestionResponse:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role not in TaskService.validation_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут подбирать теги через LLM",
            )

        task = await TaskService.get_task_or_404(project_id, task_id, db)
        available_tags = await TaskTagService.list_task_tags(project_id, db)
        if not available_tags:
            return TaskTagSuggestionResponse(suggestions=[], generated_at=datetime.now(UTC))

        try:
            return await run_task_tag_suggestion_graph(
                db=db,
                actor_user_id=current_user.id,
                project_id=project_id,
                task_id=task.id,
                title=payload.title,
                content=payload.content,
                current_tags=payload.current_tags,
                available_tags=[tag.name for tag in available_tags],
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
