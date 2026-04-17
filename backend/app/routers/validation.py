from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.task import ValidationResult
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["validation"])


@router.post("/{task_id}/validate", response_model=ValidationResult)
async def validate_task(task_id: str, current_user: CurrentUser, db: DBSession) -> ValidationResult:
    return await TaskService.validate_task(task_id, current_user, db)
