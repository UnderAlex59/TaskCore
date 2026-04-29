from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_rule import CustomRule
from app.models.project_task_tag import ProjectTaskTag
from app.models.task import Task
from app.models.task_tag import TaskTag
from app.models.user import User
from app.schemas.task_tag import (
    AdminTaskTagRead,
    ProjectTaskTagCreate,
    TaskTagCreate,
    TaskTagOptionRead,
    TaskTagUpdate,
)
from app.services.audit_service import AuditService


class TaskTagService:
    @staticmethod
    def _normalize_display_name(name: str) -> str:
        return re.sub(r"\s+", " ", name).strip()

    @staticmethod
    def _normalize_key(name: str) -> str:
        return TaskTagService._normalize_display_name(name).casefold()

    @staticmethod
    async def list_task_tags(project_id: str, db: AsyncSession) -> list[TaskTagOptionRead]:
        stmt: Select[tuple[TaskTag]] = (
            select(TaskTag)
            .join(ProjectTaskTag, ProjectTaskTag.task_tag_id == TaskTag.id)
            .where(ProjectTaskTag.project_id == project_id)
            .order_by(TaskTag.name.asc())
        )
        tags = list((await db.execute(stmt)).scalars().all())
        return [TaskTagOptionRead.model_validate(tag) for tag in tags]

    @staticmethod
    async def list_admin_task_tags(db: AsyncSession) -> list[AdminTaskTagRead]:
        tasks_count = (
            select(func.count())
            .select_from(Task)
            .where(Task.tags.any(TaskTag.name))
            .correlate(TaskTag)
            .scalar_subquery()
        )
        rules_count = (
            select(func.count())
            .select_from(CustomRule)
            .where(CustomRule.applies_to_tags.any(TaskTag.name))
            .correlate(TaskTag)
            .scalar_subquery()
        )
        stmt = (
            select(
                TaskTag,
                tasks_count.label("tasks_count"),
                rules_count.label("rules_count"),
            )
            .order_by(TaskTag.name.asc())
        )
        rows = list((await db.execute(stmt)).all())
        return [
            AdminTaskTagRead(
                id=tag.id,
                name=tag.name,
                created_by=tag.created_by,
                created_at=tag.created_at,
                updated_at=tag.updated_at,
                tasks_count=int(task_count or 0),
                rules_count=int(rule_count or 0),
            )
            for tag, task_count, rule_count in rows
        ]

    @staticmethod
    async def _get_or_create_global_tag(
        payload: TaskTagCreate,
        actor: User,
        db: AsyncSession,
    ) -> TaskTag:
        display_name = TaskTagService._normalize_display_name(payload.name)
        if not display_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Название тега не должно быть пустым",
            )

        normalized_name = TaskTagService._normalize_key(display_name)
        existing_stmt: Select[tuple[TaskTag]] = select(TaskTag).where(TaskTag.normalized_name == normalized_name)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        tag = TaskTag(
            name=display_name,
            normalized_name=normalized_name,
            created_by=actor.id,
        )
        db.add(tag)
        await db.flush()
        return tag

    @staticmethod
    async def create_task_tag(payload: TaskTagCreate, actor: User, db: AsyncSession) -> AdminTaskTagRead:
        display_name = TaskTagService._normalize_display_name(payload.name)
        if not display_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Название тега не должно быть пустым",
            )

        normalized_name = TaskTagService._normalize_key(display_name)
        existing_stmt: Select[tuple[TaskTag]] = select(TaskTag).where(TaskTag.normalized_name == normalized_name)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Тег с таким названием уже существует",
            )

        tag = TaskTag(
            name=display_name,
            normalized_name=normalized_name,
            created_by=actor.id,
        )
        db.add(tag)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.task_tag.created",
            entity_type="task_tag",
            entity_id=tag.id,
            metadata={"name": tag.name},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Тег с таким названием уже существует",
            ) from exc

        return await TaskTagService.get_admin_task_tag(tag.id, db)

    @staticmethod
    async def get_admin_task_tag(tag_id: str, db: AsyncSession) -> AdminTaskTagRead:
        rows = await TaskTagService.list_admin_task_tags(db)
        for row in rows:
            if row.id == tag_id:
                return row
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Тег не найден",
        )

    @staticmethod
    async def update_task_tag(
        tag_id: str,
        payload: TaskTagUpdate,
        actor: User,
        db: AsyncSession,
    ) -> AdminTaskTagRead:
        tag = await db.get(TaskTag, tag_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Тег не найден",
            )

        display_name = TaskTagService._normalize_display_name(payload.name)
        if not display_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Название тега не должно быть пустым",
            )

        previous_name = tag.name
        previous_key = tag.normalized_name
        next_key = TaskTagService._normalize_key(display_name)
        if previous_name == display_name and previous_key == next_key:
            return await TaskTagService.get_admin_task_tag(tag.id, db)

        tag.name = display_name
        tag.normalized_name = next_key
        await db.execute(
            update(Task)
            .where(Task.tags.any(previous_name))
            .values(tags=func.array_replace(Task.tags, previous_name, display_name))
        )
        await db.execute(
            update(CustomRule)
            .where(CustomRule.applies_to_tags.any(previous_name))
            .values(applies_to_tags=func.array_replace(CustomRule.applies_to_tags, previous_name, display_name))
        )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.task_tag.updated",
            entity_type="task_tag",
            entity_id=tag.id,
            metadata={"previous_name": previous_name, "name": display_name},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Тег с таким названием уже существует",
            ) from exc

        return await TaskTagService.get_admin_task_tag(tag.id, db)

    @staticmethod
    async def delete_task_tag(tag_id: str, actor: User, db: AsyncSession) -> None:
        tag = await db.get(TaskTag, tag_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Тег не найден",
            )

        tasks_count = int(
            (
                await db.execute(
                    select(func.count()).select_from(Task).where(Task.tags.any(tag.name))
                )
            ).scalar_one()
        )
        rules_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(CustomRule)
                    .where(CustomRule.applies_to_tags.any(tag.name))
                )
            ).scalar_one()
        )
        if tasks_count or rules_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Тег нельзя удалить, пока он используется "
                    f"в задачах ({tasks_count}) или правилах ({rules_count})"
                ),
            )

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.task_tag.deleted",
            entity_type="task_tag",
            entity_id=tag.id,
            metadata={"name": tag.name},
        )
        await db.delete(tag)
        await db.commit()

    @staticmethod
    async def add_task_tag_to_project(
        project_id: str,
        payload: ProjectTaskTagCreate,
        actor: User,
        db: AsyncSession,
    ) -> TaskTagOptionRead:
        tag = await TaskTagService._get_or_create_global_tag(payload, actor, db)
        mapping = await db.get(ProjectTaskTag, {"project_id": project_id, "task_tag_id": tag.id})
        if mapping is None:
            db.add(
                ProjectTaskTag(
                    project_id=project_id,
                    task_tag_id=tag.id,
                    created_by=actor.id,
                )
            )

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="project.task_tag.upserted",
            entity_type="project_task_tag",
            entity_id=f"{project_id}:{tag.id}",
            project_id=project_id,
            metadata={"name": tag.name},
        )
        await db.commit()
        return TaskTagOptionRead.model_validate(tag)

    @staticmethod
    async def remove_task_tag_from_project(
        project_id: str,
        tag_id: str,
        actor: User,
        db: AsyncSession,
    ) -> None:
        mapping = await db.get(ProjectTaskTag, {"project_id": project_id, "task_tag_id": tag_id})
        if mapping is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Тег проекта не найден",
            )

        tag = await db.get(TaskTag, tag_id)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Тег не найден",
            )

        tasks_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Task)
                    .where(Task.project_id == project_id, Task.tags.any(tag.name))
                )
            ).scalar_one()
        )
        rules_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(CustomRule)
                    .where(CustomRule.project_id == project_id, CustomRule.applies_to_tags.any(tag.name))
                )
            ).scalar_one()
        )
        if tasks_count or rules_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Тег нельзя убрать из проекта, пока он используется "
                    f"в задачах ({tasks_count}) или правилах ({rules_count})"
                ),
            )

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="project.task_tag.removed",
            entity_type="project_task_tag",
            entity_id=f"{project_id}:{tag.id}",
            project_id=project_id,
            metadata={"name": tag.name},
        )
        await db.delete(mapping)
        await db.commit()

    @staticmethod
    async def validate_reference_tags(project_id: str, tags: list[str], db: AsyncSession) -> list[str]:
        normalized_pairs: list[tuple[str, str]] = []
        seen_keys: set[str] = set()
        for raw_value in tags:
            display_name = TaskTagService._normalize_display_name(raw_value)
            if not display_name:
                continue
            key = TaskTagService._normalize_key(display_name)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            normalized_pairs.append((key, display_name))

        if not normalized_pairs:
            return []

        stmt: Select[tuple[TaskTag]] = select(TaskTag).where(
            TaskTag.normalized_name.in_([key for key, _ in normalized_pairs]),
            TaskTag.id.in_(
                select(ProjectTaskTag.task_tag_id).where(ProjectTaskTag.project_id == project_id)
            ),
        )
        tag_rows = list((await db.execute(stmt)).scalars().all())
        tag_by_key = {tag.normalized_name: tag for tag in tag_rows}

        missing = [display_name for key, display_name in normalized_pairs if key not in tag_by_key]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Теги не найдены в справочнике проекта: {', '.join(missing)}",
            )

        return [tag_by_key[key].name for key, _ in normalized_pairs]
