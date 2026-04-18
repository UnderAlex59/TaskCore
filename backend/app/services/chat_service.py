from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.agents.chat_agents.registry import parse_requested_agent
from app.agents.chat_graph import run_chat_graph
from app.core.database import AsyncSessionLocal
from app.models.message import Message, MessageType
from app.models.task import Task
from app.models.user import User
from app.schemas.message import MessageCreate, MessageRead
from app.services.audit_service import AuditService
from app.services.chat_realtime import chat_connection_manager, serialize_message
from app.services.task_service import TaskService


@dataclass(slots=True)
class PendingChatResponse:
    actor_user_id: str
    message_type: MessageType
    raw_message_content: str
    requested_agent: str | None
    routed_content: str
    task_content: str
    task_id: str
    task_status: str
    task_title: str
    user_message_id: str
    validation_result: dict | None


class ChatService:
    @staticmethod
    def _detect_message_type(content: str) -> MessageType:
        lowered = content.lower()
        proposal_markers = (
            "предлага",
            "измен",
            "change",
            "нужно поменять",
            "следует заменить",
        )
        if any(marker in lowered for marker in proposal_markers):
            return MessageType.CHANGE_PROPOSAL
        if content.strip().endswith("?") or any(
            marker in lowered
            for marker in ("как", "почему", "зачем", "что если", "when", "why", "how")
        ):
            return MessageType.QUESTION
        return MessageType.GENERAL

    @staticmethod
    async def list_messages(
        task_id: str,
        current_user: User,
        db: AsyncSession,
        *,
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[MessageRead]:
        await TaskService.get_task_with_chat_access(task_id, current_user, db)
        author = aliased(User)
        stmt = (
            select(Message, author.nickname, author.full_name, author.avatar_url)
            .outerjoin(author, author.id == Message.author_id)
            .where(Message.task_id == task_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(Message.created_at < before)

        rows = list((await db.execute(stmt)).all())
        rows.reverse()
        return [
            serialize_message(
                message,
                author_name=nickname or full_name,
                author_avatar_url=avatar_url,
            )
            for message, nickname, full_name, avatar_url in rows
        ]

    @staticmethod
    async def send_message(
        task_id: str,
        payload: MessageCreate,
        current_user: User,
        db: AsyncSession,
    ) -> tuple[list[MessageRead], PendingChatResponse]:
        task = await TaskService.get_task_with_chat_access(task_id, current_user, db)
        requested_agent, routed_content = parse_requested_agent(payload.content)
        message_type = ChatService._detect_message_type(routed_content)
        stripped_content = payload.content.strip()

        user_message = Message(
            task_id=task.id,
            author_id=current_user.id,
            agent_name=None,
            message_type=message_type,
            content=stripped_content,
            source_ref=None,
        )
        db.add(user_message)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="chat.message_sent",
            entity_type="message",
            entity_id=user_message.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={"message_type": message_type.value},
        )
        await db.commit()

        return (
            [
                serialize_message(
                    user_message,
                    author_name=current_user.nickname or current_user.full_name,
                    author_avatar_url=current_user.avatar_url,
                )
            ],
            PendingChatResponse(
                actor_user_id=current_user.id,
                message_type=message_type,
                raw_message_content=stripped_content,
                requested_agent=requested_agent,
                routed_content=routed_content,
                task_content=task.content,
                task_id=task.id,
                task_status=task.status.value,
                task_title=task.title,
                user_message_id=user_message.id,
                validation_result=task.validation_result,
            ),
        )

    @staticmethod
    async def process_pending_response(pending: PendingChatResponse) -> None:
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, pending.task_id)
            if task is None:
                return

            graph_state = await run_chat_graph(
                db=db,
                task_id=pending.task_id,
                project_id=task.project_id,
                actor_user_id=pending.actor_user_id,
                task_title=pending.task_title,
                task_status=pending.task_status,
                task_content=pending.task_content,
                message_type=pending.message_type.value,
                message_content=pending.routed_content,
                validation_result=task.validation_result,
                requested_agent=pending.requested_agent,
                raw_message_content=pending.raw_message_content,
                source_message_id=pending.user_message_id,
            )
            if not graph_state.get("ai_response_required"):
                return

            agent_message_type = MessageType(
                str(graph_state.get("message_type", MessageType.AGENT_ANSWER.value))
            )
            source_ref = dict(graph_state.get("source_ref", {}))

            agent_message = Message(
                task_id=pending.task_id,
                author_id=None,
                agent_name=str(graph_state.get("agent_name")),
                message_type=agent_message_type,
                content=str(graph_state.get("response")),
                source_ref=source_ref,
            )
            db.add(agent_message)
            await db.commit()
            await db.refresh(agent_message)
            await chat_connection_manager.broadcast_messages(
                pending.task_id,
                [
                    serialize_message(
                        agent_message,
                        author_name=None,
                        author_avatar_url=None,
                    )
                ],
            )
