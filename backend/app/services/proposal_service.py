from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.change_proposal import ChangeProposal, ProposalStatus
from app.models.message import Message, MessageType
from app.models.task import TaskStatus
from app.models.user import User, UserRole
from app.schemas.proposal import ProposalRead, ProposalUpdate
from app.services.audit_service import AuditService
from app.services.chat_realtime import chat_connection_manager, serialize_message
from app.services.qdrant_service import QdrantService
from app.services.task_service import TaskService
from app.services.validation_question_service import ValidationQuestionService

CHANGE_HISTORY_HEADING = "## История изменений"
LEGACY_CHANGE_HISTORY_HEADING = "## Одобренные изменения"
CHANGE_HISTORY_TITLES = {
    CHANGE_HISTORY_HEADING.removeprefix("## "),
    LEGACY_CHANGE_HISTORY_HEADING.removeprefix("## "),
}
MARKDOWN_SECTION_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class ProposalService:
    @staticmethod
    def _history_contains_accepted_change(content: str, proposal_text: str) -> bool:
        matches = list(MARKDOWN_SECTION_HEADING_PATTERN.finditer(content))
        for index, match in enumerate(matches):
            if match.group(1).strip() not in CHANGE_HISTORY_TITLES:
                continue
            section_start = match.end()
            section_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            if proposal_text in content[section_start:section_end]:
                return True
        return False

    @staticmethod
    def _append_accepted_change_to_history(content: str, proposal_text: str) -> str:
        normalized_proposal = proposal_text.strip()
        if not normalized_proposal or ProposalService._history_contains_accepted_change(
            content,
            normalized_proposal,
        ):
            return content

        stripped_content = content.rstrip()
        history_entry = f"- {normalized_proposal}"
        if not stripped_content:
            return f"{CHANGE_HISTORY_HEADING}\n{history_entry}"
        if CHANGE_HISTORY_HEADING in stripped_content:
            return f"{stripped_content}\n{history_entry}"
        return f"{stripped_content}\n\n{CHANGE_HISTORY_HEADING}\n{history_entry}"

    @staticmethod
    async def create_from_message(
        task_id: str,
        *,
        project_id: str | None,
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
        if project_id is not None:
            await QdrantService.upsert_proposal(
                proposal_id=proposal.id,
                task_id=task_id,
                project_id=project_id,
                proposal_text=proposal_text,
                status=proposal.status.value,
            )
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
        current_timestamp = datetime.now(UTC)
        proposal.reviewed_at = current_timestamp

        if proposal.status == ProposalStatus.ACCEPTED:
            task.content = ProposalService._append_accepted_change_to_history(
                task.content,
                proposal.proposal_text,
            )
            task.validation_result = None
            await ValidationQuestionService.clear_for_task(task.id, db)
            task.status = TaskStatus.NEEDS_REWORK

        if proposal.status == ProposalStatus.ACCEPTED:
            task.updated_at = current_timestamp

        await QdrantService.upsert_proposal(
            proposal_id=proposal.id,
            task_id=task.id,
            project_id=task.project_id,
            proposal_text=proposal.proposal_text,
            status=proposal.status.value,
        )

        status_text = "принято" if proposal.status == ProposalStatus.ACCEPTED else "отклонено"
        status_message = Message(
            task_id=task.id,
            author_id=None,
            agent_name="ChangeTrackerAgent",
            message_type=MessageType.AGENT_PROPOSAL,
            content=f"Предложение {status_text} пользователем {current_user.full_name}.",
            source_ref={
                "proposal_id": proposal.id,
                "collection": "change_proposals",
                "proposal_status": proposal.status.value,
                "proposal_text": proposal.proposal_text,
                "reviewed_by_name": current_user.full_name,
            },
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
