from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.models.message import Message
from app.schemas.message import MessageRead


def serialize_message(
    message: Message,
    *,
    author_name: str | None,
    author_avatar_url: str | None,
) -> MessageRead:
    return MessageRead(
        id=message.id,
        task_id=message.task_id,
        author_id=message.author_id,
        author_name=author_name,
        author_avatar_url=author_avatar_url,
        agent_name=message.agent_name,
        message_type=message.message_type.value,
        content=message.content,
        source_ref=message.source_ref,
        created_at=message.created_at,
    )


class ChatConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[task_id].add(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        task_connections = self._connections.get(task_id)
        if task_connections is None:
            return

        task_connections.discard(websocket)
        if not task_connections:
            self._connections.pop(task_id, None)

    async def broadcast_messages(self, task_id: str, messages: list[MessageRead]) -> None:
        if not messages:
            return

        task_connections = list(self._connections.get(task_id, set()))
        if not task_connections:
            return

        payload = {
            "type": "messages.created",
            "messages": [message.model_dump(mode="json") for message in messages],
        }
        disconnected: list[WebSocket] = []

        for websocket in task_connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(task_id, websocket)


chat_connection_manager = ChatConnectionManager()
