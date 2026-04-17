from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageRead(BaseModel):
    id: str
    task_id: str
    author_id: str | None
    author_name: str | None
    author_avatar_url: str | None
    agent_name: str | None
    message_type: str
    content: str
    source_ref: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
