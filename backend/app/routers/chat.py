from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.message import MessageCreate, MessageRead
from app.services.chat_service import ChatService

router = APIRouter(prefix="/tasks", tags=["chat"])


@router.get("/{task_id}/messages", response_model=list[MessageRead])
async def list_messages(
    task_id: str,
    current_user: CurrentUser,
    db: DBSession,
    before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[MessageRead]:
    return await ChatService.list_messages(task_id, current_user, db, before=before, limit=limit)


@router.post("/{task_id}/messages", response_model=list[MessageRead], status_code=201)
async def send_message(
    task_id: str,
    payload: MessageCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> list[MessageRead]:
    return await ChatService.send_message(task_id, payload, current_user, db)
