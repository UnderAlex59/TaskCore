from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_rule import CustomRule
from app.models.project import Project, ProjectMember
from app.models.user import User, UserRole
from app.schemas.project import (
    CustomRuleCreate,
    CustomRuleRead,
    CustomRuleUpdate,
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
)
from app.services.audit_service import AuditService


class ProjectService:
    manager_roles = {UserRole.MANAGER, UserRole.ADMIN}

    @staticmethod
    async def get_project_or_404(project_id: str, db: AsyncSession) -> Project:
        project = await db.get(Project, project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проект не найден",
            )
        return project

    @staticmethod
    async def get_membership(project_id: str, user_id: str, db: AsyncSession) -> ProjectMember | None:
        stmt: Select[tuple[ProjectMember]] = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def ensure_project_access(project_id: str, current_user: User, db: AsyncSession) -> Project:
        project = await ProjectService.get_project_or_404(project_id, db)
        if current_user.role == UserRole.ADMIN:
            return project

        membership = await ProjectService.get_membership(project_id, current_user.id, db)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="У вас нет доступа к этому проекту",
            )
        return project

    @staticmethod
    async def ensure_project_manager(project_id: str, current_user: User, db: AsyncSession) -> Project:
        project = await ProjectService.ensure_project_access(project_id, current_user, db)
        if current_user.role == UserRole.ADMIN:
            return project

        membership = await ProjectService.get_membership(project_id, current_user.id, db)
        if membership is None or membership.role not in ProjectService.manager_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нужны права менеджера проекта",
            )
        return project

    @staticmethod
    async def list_projects(current_user: User, db: AsyncSession) -> list[ProjectRead]:
        if current_user.role == UserRole.ADMIN:
            stmt: Select[tuple[Project]] = select(Project).order_by(Project.updated_at.desc())
        else:
            stmt = (
                select(Project)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == current_user.id)
                .order_by(Project.updated_at.desc())
            )

        projects = list((await db.execute(stmt)).scalars().all())
        return [ProjectRead.model_validate(project) for project in projects]

    @staticmethod
    async def create_project(payload: ProjectCreate, current_user: User, db: AsyncSession) -> ProjectRead:
        project = Project(
            name=payload.name,
            description=payload.description,
            created_by=current_user.id,
        )
        db.add(project)
        await db.flush()

        # The creator always becomes a project manager to avoid a second bootstrap step.
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=current_user.id,
                role=UserRole.MANAGER,
            )
        )
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="project.created",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
        )
        await db.commit()
        await db.refresh(project)
        return ProjectRead.model_validate(project)

    @staticmethod
    async def get_project(project_id: str, current_user: User, db: AsyncSession) -> ProjectRead:
        project = await ProjectService.ensure_project_access(project_id, current_user, db)
        return ProjectRead.model_validate(project)

    @staticmethod
    async def update_project(
        project_id: str,
        payload: ProjectUpdate,
        current_user: User,
        db: AsyncSession,
    ) -> ProjectRead:
        project = await ProjectService.ensure_project_manager(project_id, current_user, db)
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field_name, value)

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="project.updated",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
        )
        await db.commit()
        await db.refresh(project)
        return ProjectRead.model_validate(project)

    @staticmethod
    async def delete_project(project_id: str, current_user: User, db: AsyncSession) -> None:
        project = await ProjectService.get_project_or_404(project_id, db)
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="project.deleted",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
        )
        await db.delete(project)
        await db.commit()

    @staticmethod
    async def list_members(project_id: str, current_user: User, db: AsyncSession) -> list[ProjectMemberRead]:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        stmt = (
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.joined_at.asc())
        )
        rows: Sequence[tuple[ProjectMember, User]] = (await db.execute(stmt)).all()
        return [
            ProjectMemberRead(
                project_id=membership.project_id,
                user_id=membership.user_id,
                role=membership.role,
                joined_at=membership.joined_at,
                full_name=user.full_name,
                email=user.email,
                global_role=user.role,
            )
            for membership, user in rows
        ]

    @staticmethod
    async def add_member(
        project_id: str,
        payload: ProjectMemberCreate,
        current_user: User,
        db: AsyncSession,
    ) -> ProjectMemberRead:
        await ProjectService.ensure_project_manager(project_id, current_user, db)
        role = UserRole(payload.role)

        user = await db.get(User, payload.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        membership = await ProjectService.get_membership(project_id, payload.user_id, db)
        if membership is None:
            membership = ProjectMember(project_id=project_id, user_id=payload.user_id, role=role)
            db.add(membership)
        else:
            membership.role = role

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="project.member_upserted",
            entity_type="project_member",
            entity_id=f"{project_id}:{payload.user_id}",
            project_id=project_id,
            metadata={"role": role.value, "user_id": payload.user_id},
        )
        await db.commit()
        await db.refresh(membership)
        return ProjectMemberRead(
            project_id=membership.project_id,
            user_id=membership.user_id,
            role=membership.role,
            joined_at=membership.joined_at,
            full_name=user.full_name,
            email=user.email,
            global_role=user.role,
        )

    @staticmethod
    async def remove_member(project_id: str, user_id: str, current_user: User, db: AsyncSession) -> None:
        await ProjectService.ensure_project_manager(project_id, current_user, db)
        membership = await ProjectService.get_membership(project_id, user_id, db)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Участник проекта не найден",
            )

        if membership.role == UserRole.MANAGER:
            stmt = select(func.count()).select_from(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == UserRole.MANAGER,
            )
            manager_count = (await db.execute(stmt)).scalar_one()
            if manager_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="В проекте должен остаться хотя бы один менеджер",
                )

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="project.member_removed",
            entity_type="project_member",
            entity_id=f"{project_id}:{user_id}",
            project_id=project_id,
            metadata={"user_id": user_id},
        )
        await db.delete(membership)
        await db.commit()

    @staticmethod
    async def list_rules(project_id: str, current_user: User, db: AsyncSession) -> list[CustomRuleRead]:
        await ProjectService.ensure_project_access(project_id, current_user, db)
        stmt: Select[tuple[CustomRule]] = (
            select(CustomRule)
            .where(CustomRule.project_id == project_id)
            .order_by(CustomRule.created_at.desc())
        )
        rules = list((await db.execute(stmt)).scalars().all())
        return [CustomRuleRead.model_validate(rule) for rule in rules]

    @staticmethod
    async def get_active_rules(project_id: str, tags: list[str], db: AsyncSession) -> list[CustomRule]:
        stmt: Select[tuple[CustomRule]] = (
            select(CustomRule)
            .where(CustomRule.project_id == project_id, CustomRule.is_active.is_(True))
            .order_by(CustomRule.created_at.asc())
        )
        rules = list((await db.execute(stmt)).scalars().all())
        if not tags:
            return [rule for rule in rules if not rule.applies_to_tags]

        return [
            rule
            for rule in rules
            if not rule.applies_to_tags or bool(set(rule.applies_to_tags).intersection(tags))
        ]

    @staticmethod
    async def create_rule(
        project_id: str,
        payload: CustomRuleCreate,
        current_user: User,
        db: AsyncSession,
    ) -> CustomRuleRead:
        await ProjectService.get_project_or_404(project_id, db)
        rule = CustomRule(
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            applies_to_tags=payload.applies_to_tags,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
        db.add(rule)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="rule.created",
            entity_type="custom_rule",
            entity_id=rule.id,
            project_id=project_id,
        )
        await db.commit()
        await db.refresh(rule)
        return CustomRuleRead.model_validate(rule)

    @staticmethod
    async def update_rule(
        project_id: str,
        rule_id: str,
        payload: CustomRuleUpdate,
        current_user: User,
        db: AsyncSession,
    ) -> CustomRuleRead:
        rule = await db.get(CustomRule, rule_id)
        if rule is None or rule.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Правило не найдено",
            )

        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(rule, field_name, value)

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="rule.updated",
            entity_type="custom_rule",
            entity_id=rule.id,
            project_id=project_id,
        )
        await db.commit()
        await db.refresh(rule)
        return CustomRuleRead.model_validate(rule)

    @staticmethod
    async def delete_rule(project_id: str, rule_id: str, current_user: User, db: AsyncSession) -> None:
        rule = await db.get(CustomRule, rule_id)
        if rule is None or rule.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Правило не найдено",
            )

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="rule.deleted",
            entity_type="custom_rule",
            entity_id=rule.id,
            project_id=project_id,
        )
        await db.delete(rule)
        await db.commit()
