from __future__ import annotations

from typing import Literal

from fastapi import (
    APIRouter,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from jose import JWTError

from app.core.database import AsyncSessionLocal
from app.core.dependencies import CurrentUser, DBSession
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.notification import (
    ChatUnreadRead,
    NotificationPageRead,
    NotificationRead,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
)
from app.services.notification_realtime import notification_connection_manager
from app.services.notification_service import NotificationService

router = APIRouter(tags=["notifications"])


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


@router.get("/notifications", response_model=NotificationPageRead)
async def list_notifications(
    current_user: CurrentUser,
    db: DBSession,
    unread_only: bool = Query(default=False),
    read_state: Literal["all", "unread", "read"] = Query(default="all"),
    priority: Literal["normal", "important"] | None = Query(default=None),
    type: Literal[
        "qa_needs_analyst",
        "analyst_requested",
        "task_assigned",
        "task_status_changed",
        "chat_mention",
    ]
    | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
) -> NotificationPageRead:
    return await NotificationService.list_notifications(
        current_user,
        db,
        unread_only=unread_only,
        read_state=read_state,
        priority=priority,
        type_=type,
        search=search,
        limit=limit,
    )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> NotificationRead:
    return await NotificationService.mark_read(notification_id, current_user, db)


@router.post("/notifications/read-all", status_code=204)
async def mark_all_notifications_read(current_user: CurrentUser, db: DBSession) -> None:
    await NotificationService.mark_all_read(current_user, db)


@router.get("/users/me/notification-settings", response_model=NotificationSettingsRead)
async def get_notification_settings(
    current_user: CurrentUser,
    db: DBSession,
) -> NotificationSettingsRead:
    return await NotificationService.get_settings(current_user, db)


@router.patch("/users/me/notification-settings", response_model=NotificationSettingsRead)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> NotificationSettingsRead:
    return await NotificationService.update_settings(current_user, payload, db)


@router.get("/tasks/{task_id}/chat-unread", response_model=ChatUnreadRead)
async def get_task_chat_unread(
    task_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> ChatUnreadRead:
    return await NotificationService.get_task_unread_state(task_id, current_user, db)


@router.post("/tasks/{task_id}/chat-read", response_model=ChatUnreadRead)
async def mark_task_chat_read(
    task_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> ChatUnreadRead:
    return await NotificationService.mark_task_chat_read(task_id, current_user, db)


@router.post(
    "/tasks/{task_id}/messages/{message_id}/request-analyst",
    response_model=NotificationRead,
)
async def request_analyst(
    task_id: str,
    message_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> NotificationRead:
    return await NotificationService.request_analyst(task_id, message_id, current_user, db)


@router.websocket("/notifications/ws")
async def stream_notifications(websocket: WebSocket) -> None:
    async with AsyncSessionLocal() as db:
        current_user = await _get_websocket_user(websocket, db)
        await notification_connection_manager.connect(current_user.id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            notification_connection_manager.disconnect(current_user.id, websocket)
