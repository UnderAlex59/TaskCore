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
    def _initial_source_ref(requested_agent: str | None) -> dict | None:
        if requested_agent is None:
            return None
        return {
            "routing": {
                "mode": "forced",
                "status": "pending",
                "ai_response_required": True,
                "target_agent_key": None,
                "message_type": MessageType.GENERAL.value,
                "reason": "forced_agent_pending",
                "requested_agent": requested_agent,
            }
        }

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
        stripped_content = payload.content.strip()

        user_message = Message(
            task_id=task.id,
            author_id=current_user.id,
            agent_name=None,
            message_type=MessageType.GENERAL,
            content=stripped_content,
            source_ref=ChatService._initial_source_ref(requested_agent),
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
            metadata={"message_type": MessageType.GENERAL.value},
        )
        from app.services.notification_service import NotificationService

        await NotificationService.notify_mentions_for_message(task, user_message, current_user, db)
        await db.commit()
        await NotificationService.notify_chat_unread_for_message(task, user_message, db)

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
    async def _apply_source_message_routing(
        db: AsyncSession,
        *,
        source_message_id: str | None,
        routing_source_ref: dict,
    ) -> MessageRead | None:
        routing = dict(routing_source_ref.get("routing", {}))
        if not source_message_id or not routing:
            return None

        source_message = await db.get(Message, source_message_id)
        if source_message is None:
            return None

        source_ref = dict(source_message.source_ref or {})
        source_ref["routing"] = routing
        source_message.source_ref = source_ref
        await db.flush()

        author = await db.get(User, source_message.author_id) if source_message.author_id else None
        return serialize_message(
            source_message,
            author_name=(author.nickname or author.full_name) if author else None,
            author_avatar_url=author.avatar_url if author else None,
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
                message_type=MessageType.GENERAL.value,
                message_content=pending.routed_content,
                validation_result=task.validation_result,
                requested_agent=pending.requested_agent,
                raw_message_content=pending.raw_message_content,
                source_message_id=pending.user_message_id,
            )
            updated_source_message = await ChatService._apply_source_message_routing(
                db,
                source_message_id=pending.user_message_id,
                routing_source_ref=dict(graph_state.get("source_ref", {})),
            )
            if not graph_state.get("ai_response_required"):
                await db.commit()
                if updated_source_message is not None:
                    await chat_connection_manager.broadcast_messages(
                        pending.task_id,
                        [updated_source_message],
                    )
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
            await db.flush()
            from app.services.notification_service import NotificationService

            source_ref_for_notifications = dict(agent_message.source_ref or {})
            if (
                agent_message.agent_name == "QAAgent"
                and (
                    source_ref_for_notifications.get("answer_confidence") == "low"
                    or source_ref_for_notifications.get("validation_backlog_question")
                    or source_ref_for_notifications.get("validation_backlog_saved") is True
                )
            ):
                await NotificationService.notify_qa_needs_analyst(task, agent_message, db)
            await db.commit()
            await db.refresh(agent_message)
            if updated_source_message is not None:
                source_message = await db.get(Message, updated_source_message.id)
                if source_message is not None:
                    author = (
                        await db.get(User, source_message.author_id)
                        if source_message.author_id
                        else None
                    )
                    updated_source_message = serialize_message(
                        source_message,
                        author_name=(author.nickname or author.full_name) if author else None,
                        author_avatar_url=author.avatar_url if author else None,
                    )
            await chat_connection_manager.broadcast_messages(
                pending.task_id,
                [
                    *([updated_source_message] if updated_source_message is not None else []),
                    serialize_message(
                        agent_message,
                        author_name=None,
                        author_avatar_url=None,
                    )
                ],
            )
            await NotificationService.notify_chat_unread_for_message(task, agent_message, db)
