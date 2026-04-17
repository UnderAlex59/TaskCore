from __future__ import annotations

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession
from app.models.task import TaskStatus
from app.schemas.task import TaskApprove, TaskAttachmentRead, TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

settings = get_settings()
router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    project_id: str,
    current_user: CurrentUser,
    db: DBSession,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    tags: list[str] | None = Query(default=None),
    analyst_id: str | None = Query(default=None),
    developer_id: str | None = Query(default=None),
    tester_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> list[TaskRead]:
    return await TaskService.list_tasks(
        project_id,
        current_user,
        db,
        status_filter=status_filter,
        tags=tags,
        analyst_id=analyst_id,
        developer_id=developer_id,
        tester_id=tester_id,
        search=search,
        page=page,
        size=size,
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskRead:
    return await TaskService.create_task(project_id, payload, current_user, db)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(project_id: str, task_id: str, current_user: CurrentUser, db: DBSession) -> TaskRead:
    return await TaskService.get_task(project_id, task_id, current_user, db)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    project_id: str,
    task_id: str,
    payload: TaskUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskRead:
    return await TaskService.update_task(project_id, task_id, payload, current_user, db)


@router.post("/{task_id}/approve", response_model=TaskRead)
async def approve_task(
    project_id: str,
    task_id: str,
    payload: TaskApprove,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskRead:
    return await TaskService.approve_task(task_id, payload, current_user, db)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_task(project_id: str, task_id: str, current_user: CurrentUser, db: DBSession) -> Response:
    await TaskService.delete_task(project_id, task_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/attachments", response_model=TaskAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    project_id: str,
    task_id: str,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
) -> TaskAttachmentRead:
    return await TaskService.upload_attachment(
        project_id,
        task_id,
        file,
        current_user,
        db,
        settings.UPLOAD_DIR,
    )
