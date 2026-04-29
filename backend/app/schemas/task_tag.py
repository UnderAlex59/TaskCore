from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")


class TaskTagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")


class TaskTagOptionRead(BaseModel):
    id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProjectTaskTagCreate(TaskTagCreate):
    pass


class AdminTaskTagRead(TaskTagOptionRead):
    created_by: str
    created_at: datetime
    updated_at: datetime
    tasks_count: int = 0
    rules_count: int = 0
