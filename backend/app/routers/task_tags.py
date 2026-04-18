from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.task_tag import TaskTagOptionRead
from app.services.task_tag_service import TaskTagService

router = APIRouter(prefix="/task-tags", tags=["task-tags"])


@router.get("", response_model=list[TaskTagOptionRead])
async def list_task_tags(
    _: CurrentUser,
    db: DBSession,
) -> list[TaskTagOptionRead]:
    return await TaskTagService.list_task_tags(db)
