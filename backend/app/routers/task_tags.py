from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import CurrentUser, DBSession, require_role
from app.models.user import User, UserRole
from app.schemas.task_tag import ProjectTaskTagCreate, TaskTagOptionRead
from app.services.project_service import ProjectService
from app.services.task_tag_service import TaskTagService

router = APIRouter(prefix="/projects/{project_id}/task-tags", tags=["task-tags"])


@router.get("", response_model=list[TaskTagOptionRead])
async def list_task_tags(
    project_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[TaskTagOptionRead]:
    await ProjectService.ensure_project_access(project_id, current_user, db)
    return await TaskTagService.list_task_tags(project_id, db)


@router.post("", response_model=TaskTagOptionRead, status_code=status.HTTP_201_CREATED)
async def add_project_task_tag(
    project_id: str,
    payload: ProjectTaskTagCreate,
    current_user: Annotated[
        User,
        Depends(require_role(UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN)),
    ],
    db: DBSession,
) -> TaskTagOptionRead:
    await ProjectService.ensure_project_manager(project_id, current_user, db)
    return await TaskTagService.add_task_tag_to_project(project_id, payload, current_user, db)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_project_task_tag(
    project_id: str,
    tag_id: str,
    current_user: Annotated[
        User,
        Depends(require_role(UserRole.ANALYST, UserRole.MANAGER, UserRole.ADMIN)),
    ],
    db: DBSession,
) -> Response:
    await ProjectService.ensure_project_manager(project_id, current_user, db)
    await TaskTagService.remove_task_tag_from_project(project_id, tag_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
