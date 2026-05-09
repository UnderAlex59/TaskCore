from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.schemas.notification import NotificationRead


class NotificationConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        user_connections = self._connections.get(user_id)
        if user_connections is None:
            return

        user_connections.discard(websocket)
        if not user_connections:
            self._connections.pop(user_id, None)

    async def broadcast_notifications(
        self,
        user_id: str,
        notifications: list[NotificationRead],
    ) -> None:
        if not notifications:
            return
        await self._send(
            user_id,
            {
                "type": "notifications.created",
                "notifications": [item.model_dump(mode="json") for item in notifications],
            },
        )

    async def broadcast_chat_unread(self, user_id: str, task_id: str, unread_count: int) -> None:
        await self._send(
            user_id,
            {
                "type": "chat.unread.changed",
                "task_id": task_id,
                "unread_count": unread_count,
            },
        )

    async def _send(self, user_id: str, payload: dict) -> None:
        user_connections = list(self._connections.get(user_id, set()))
        if not user_connections:
            return

        disconnected: list[WebSocket] = []
        for websocket in user_connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(user_id, websocket)


notification_connection_manager = NotificationConnectionManager()
