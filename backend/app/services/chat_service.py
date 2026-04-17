from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.agents.chat_agents.registry import parse_requested_agent
from app.agents.chat_graph import run_chat_graph
from app.models.message import Message, MessageType
from app.models.user import User
from app.schemas.message import MessageCreate, MessageRead
from app.services.audit_service import AuditService
from app.services.rag_service import RagService
from app.services.task_service import TaskService


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
    def _serialize(
        message: Message,
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
            ChatService._serialize(message, nickname or full_name, avatar_url)
            for message, nickname, full_name, avatar_url in rows
        ]

    @staticmethod
    async def send_message(
        task_id: str,
        payload: MessageCreate,
        current_user: User,
        db: AsyncSession,
    ) -> list[MessageRead]:
        task = await TaskService.get_task_with_chat_access(task_id, current_user, db)
        requested_agent, routed_content = parse_requested_agent(payload.content)
        message_type = ChatService._detect_message_type(routed_content)

        user_message = Message(
            task_id=task.id,
            author_id=current_user.id,
            agent_name=None,
            message_type=message_type,
            content=payload.content.strip(),
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

        messages = [
            ChatService._serialize(
                user_message,
                current_user.nickname or current_user.full_name,
                current_user.avatar_url,
            )
        ]
        if message_type == MessageType.GENERAL and requested_agent is None:
            await db.commit()
            return messages

        related_tasks = await RagService.search_related_tasks(
            db,
            project_id=task.project_id,
            query_text=f"{task.title}\n{routed_content}",
            exclude_task_id=task.id,
            limit=3,
        )
        related_tasks_for_agents: list[dict[str, object]] = [
            {key: value for key, value in item.items()} for item in related_tasks
        ]
        graph_state = await run_chat_graph(
            db=db,
            task_id=task.id,
            project_id=task.project_id,
            actor_user_id=current_user.id,
            task_title=task.title,
            task_status=task.status.value,
            task_content=task.content,
            message_type=message_type.value,
            message_content=routed_content,
            validation_result=task.validation_result,
            related_tasks=related_tasks_for_agents,
            requested_agent=requested_agent,
            raw_message_content=payload.content,
        )
        agent_message_type = MessageType(
            str(graph_state.get("message_type", MessageType.AGENT_ANSWER.value))
        )

        has_proposal = graph_state.get("proposal_text") is not None
        if has_proposal or agent_message_type == MessageType.AGENT_PROPOSAL:
            from app.services.proposal_service import ProposalService

            proposal = await ProposalService.create_from_message(
                task.id,
                source_message_id=user_message.id,
                proposed_by=current_user.id,
                proposal_text=str(graph_state.get("proposal_text", routed_content)),
                db=db,
            )
            AuditService.record(
                db,
                actor_user_id=current_user.id,
                event_type="chat.proposal_requested",
                entity_type="change_proposal",
                entity_id=proposal.id,
                project_id=task.project_id,
                task_id=task.id,
                metadata={"source_message_id": user_message.id},
            )
            source_ref = dict(graph_state.get("source_ref", {}))
            source_ref["proposal_id"] = proposal.id
        else:
            source_ref = dict(graph_state.get("source_ref", {}))

        agent_message = Message(
            task_id=task.id,
            author_id=None,
            agent_name=str(graph_state.get("agent_name")),
            message_type=agent_message_type,
            content=str(graph_state.get("response")),
            source_ref=source_ref,
        )
        db.add(agent_message)
        await db.commit()
        await db.refresh(agent_message)
        messages.append(ChatService._serialize(agent_message, None, None))
        return messages
