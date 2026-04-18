from __future__ import annotations

from datetime import datetime

from jose import JWTError

from fastapi import APIRouter, BackgroundTasks, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

from app.core.database import AsyncSessionLocal
from app.core.dependencies import CurrentUser, DBSession
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.message import MessageCreate, MessageRead
from app.services.chat_realtime import chat_connection_manager
from app.services.chat_service import ChatService
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["chat"])


async def _get_websocket_user(websocket: WebSocket, db: DBSession) -> User:
    token = websocket.query_params.get("token")
    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing access token",
        )

    try:
        payload = decode_access_token(token)
        user_id = payload["sub"]
    except (JWTError, KeyError) as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid access token",
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Inactive user",
        )

    return user


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
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DBSession,
) -> list[MessageRead]:
    messages, pending = await ChatService.send_message(task_id, payload, current_user, db)
    await chat_connection_manager.broadcast_messages(task_id, messages)
    background_tasks.add_task(ChatService.process_pending_response, pending)
    return messages


@router.websocket("/{task_id}/messages/ws")
async def stream_messages(websocket: WebSocket, task_id: str) -> None:
    async with AsyncSessionLocal() as db:
        current_user = await _get_websocket_user(websocket, db)
        await TaskService.get_task_with_chat_access(task_id, current_user, db)
        await chat_connection_manager.connect(task_id, websocket)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            chat_connection_manager.disconnect(task_id, websocket)
