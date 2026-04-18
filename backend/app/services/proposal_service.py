from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.change_proposal import ChangeProposal, ProposalStatus
from app.models.message import Message, MessageType
from app.models.task import TaskStatus
from app.models.user import User, UserRole
from app.schemas.proposal import ProposalRead, ProposalUpdate
from app.services.audit_service import AuditService
from app.services.chat_realtime import chat_connection_manager, serialize_message
from app.services.task_service import TaskService
from app.services.validation_question_service import ValidationQuestionService


class ProposalService:
    @staticmethod
    async def create_from_message(
        task_id: str,
        *,
        source_message_id: str,
        proposed_by: str,
        proposal_text: str,
        db: AsyncSession,
    ) -> ChangeProposal:
        proposal = ChangeProposal(
            task_id=task_id,
            source_message_id=source_message_id,
            proposed_by=proposed_by,
            proposal_text=proposal_text,
        )
        db.add(proposal)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=proposed_by,
            event_type="proposal.created",
            entity_type="change_proposal",
            entity_id=proposal.id,
            task_id=task_id,
            metadata={"source_message_id": source_message_id},
        )
        return proposal

    @staticmethod
    def _serialize(
        proposal: ChangeProposal,
        proposed_by_name: str | None,
        reviewed_by_name: str | None,
    ) -> ProposalRead:
        return ProposalRead(
            id=proposal.id,
            task_id=proposal.task_id,
            source_message_id=proposal.source_message_id,
            proposed_by=proposal.proposed_by,
            proposed_by_name=proposed_by_name,
            proposal_text=proposal.proposal_text,
            status=proposal.status.value,
            reviewed_by=proposal.reviewed_by,
            reviewed_by_name=reviewed_by_name,
            reviewed_at=proposal.reviewed_at,
            created_at=proposal.created_at,
        )

    @staticmethod
    async def list_proposals(
        task_id: str,
        current_user: User,
        db: AsyncSession,
        *,
        status_filter: ProposalStatus | None = None,
    ) -> list[ProposalRead]:
        await TaskService.get_task_with_access(task_id, current_user, db)
        proposed_by_user = aliased(User)
        reviewed_by_user = aliased(User)
        stmt = (
            select(ChangeProposal, proposed_by_user.full_name, reviewed_by_user.full_name)
            .outerjoin(proposed_by_user, proposed_by_user.id == ChangeProposal.proposed_by)
            .outerjoin(reviewed_by_user, reviewed_by_user.id == ChangeProposal.reviewed_by)
            .where(ChangeProposal.task_id == task_id)
            .order_by(ChangeProposal.created_at.desc())
        )
        if status_filter is not None:
            stmt = stmt.where(ChangeProposal.status == status_filter)

        rows = (await db.execute(stmt)).all()
        return [
            ProposalService._serialize(proposal, proposed_by_name, reviewed_by_name)
            for proposal, proposed_by_name, reviewed_by_name in rows
        ]

    @staticmethod
    async def update_proposal(
        task_id: str,
        proposal_id: str,
        payload: ProposalUpdate,
        current_user: User,
        db: AsyncSession,
    ) -> ProposalRead:
        task = await TaskService.get_task_with_access(task_id, current_user, db)
        if current_user.role not in {UserRole.ADMIN, UserRole.ANALYST}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только аналитики и администраторы могут рассматривать предложения",
            )

        proposal = await db.get(ChangeProposal, proposal_id)
        if proposal is None or proposal.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Предложение не найдено",
            )

        proposal.status = ProposalStatus(payload.status)
        proposal.reviewed_by = current_user.id
        proposal.reviewed_at = datetime.now(timezone.utc)

        if proposal.status == ProposalStatus.ACCEPTED:
            if proposal.proposal_text not in task.content:
                separator = "\n\n## Одобренные изменения\n"
                task.content = f"{task.content.rstrip()}{separator}- {proposal.proposal_text.strip()}"
            task.validation_result = None
            await ValidationQuestionService.clear_for_task(task.id, db)
            task.status = TaskStatus.NEEDS_REWORK

        status_message = Message(
            task_id=task.id,
            author_id=None,
            agent_name="ChangeTrackerAgent",
            message_type=MessageType.AGENT_PROPOSAL,
            content=(
                f"Предложение `{proposal.id}` переведено в статус `{proposal.status.value}` "
                f"пользователем {current_user.full_name}."
            ),
            source_ref={"proposal_id": proposal.id, "collection": "change_proposals"},
        )
        db.add(status_message)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="proposal.reviewed",
            entity_type="change_proposal",
            entity_id=proposal.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={"status": proposal.status.value},
        )
        await db.commit()
        await db.refresh(proposal)
        await chat_connection_manager.broadcast_messages(
            task.id,
            [
                serialize_message(
                    status_message,
                    author_name=None,
                    author_avatar_url=None,
                )
            ],
        )
        return ProposalService._serialize(proposal, None, current_user.full_name)
