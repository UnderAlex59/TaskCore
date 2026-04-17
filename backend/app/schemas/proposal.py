from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProposalRead(BaseModel):
    id: str
    task_id: str
    source_message_id: str | None
    proposed_by: str | None
    proposed_by_name: str | None
    proposal_text: str
    status: str
    reviewed_by: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalUpdate(BaseModel):
    status: Literal["accepted", "rejected"]
