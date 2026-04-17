from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.models.change_proposal import ProposalStatus
from app.schemas.proposal import ProposalRead, ProposalUpdate
from app.services.proposal_service import ProposalService

router = APIRouter(prefix="/tasks", tags=["proposals"])


@router.get("/{task_id}/proposals", response_model=list[ProposalRead])
async def list_proposals(
    task_id: str,
    current_user: CurrentUser,
    db: DBSession,
    status_filter: ProposalStatus | None = Query(default=None, alias="status"),
) -> list[ProposalRead]:
    return await ProposalService.list_proposals(task_id, current_user, db, status_filter=status_filter)


@router.patch("/{task_id}/proposals/{proposal_id}", response_model=ProposalRead)
async def update_proposal(
    task_id: str,
    proposal_id: str,
    payload: ProposalUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> ProposalRead:
    return await ProposalService.update_proposal(task_id, proposal_id, payload, current_user, db)
