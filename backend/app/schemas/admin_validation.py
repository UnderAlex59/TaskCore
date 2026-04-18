from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class ValidationQuestionRead(BaseModel):
    id: str
    task_id: str
    project_id: str
    project_name: str
    task_title: str
    task_status: TaskStatus
    tags: list[str] = Field(default_factory=list)
    question_text: str
    validation_verdict: Literal["approved", "needs_rework"]
    validated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class ValidationQuestionPageRead(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ValidationQuestionRead]
