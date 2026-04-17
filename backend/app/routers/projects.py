from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import CurrentUser, DBSession, require_role
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
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(current_user: CurrentUser, db: DBSession) -> list[ProjectRead]:
    return await ProjectService.list_projects(current_user, db)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN))],
    db: DBSession,
) -> ProjectRead:
    return await ProjectService.create_project(payload, current_user, db)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, current_user: CurrentUser, db: DBSession) -> ProjectRead:
    return await ProjectService.get_project(project_id, current_user, db)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> ProjectRead:
    return await ProjectService.update_project(project_id, payload, current_user, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_project(
    project_id: str,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: DBSession,
) -> Response:
    await ProjectService.delete_project(project_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
async def list_members(project_id: str, current_user: CurrentUser, db: DBSession) -> list[ProjectMemberRead]:
    return await ProjectService.list_members(project_id, current_user, db)


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: str,
    payload: ProjectMemberCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> ProjectMemberRead:
    return await ProjectService.add_member(project_id, payload, current_user, db)


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_member(
    project_id: str,
    user_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> Response:
    await ProjectService.remove_member(project_id, user_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/rules", response_model=list[CustomRuleRead])
async def list_rules(project_id: str, current_user: CurrentUser, db: DBSession) -> list[CustomRuleRead]:
    return await ProjectService.list_rules(project_id, current_user, db)


@router.post("/{project_id}/rules", response_model=CustomRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    project_id: str,
    payload: CustomRuleCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: DBSession,
) -> CustomRuleRead:
    return await ProjectService.create_rule(project_id, payload, current_user, db)


@router.patch("/{project_id}/rules/{rule_id}", response_model=CustomRuleRead)
async def update_rule(
    project_id: str,
    rule_id: str,
    payload: CustomRuleUpdate,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: DBSession,
) -> CustomRuleRead:
    return await ProjectService.update_rule(project_id, rule_id, payload, current_user, db)


@router.delete(
    "/{project_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_rule(
    project_id: str,
    rule_id: str,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: DBSession,
) -> Response:
    await ProjectService.delete_rule(project_id, rule_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
