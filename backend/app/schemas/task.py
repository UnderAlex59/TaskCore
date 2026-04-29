from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    content: str = ""
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    content: str | None = None
    tags: list[str] | None = None

    model_config = ConfigDict(extra="forbid")


class TaskApprove(BaseModel):
    developer_id: str | None = None
    tester_id: str | None = None
    reviewer_analyst_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class TaskAttachmentRead(BaseModel):
    id: str
    task_id: str
    filename: str
    content_type: str
    storage_path: str
    alt_text: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskTagSuggestionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    content: str = ""
    current_tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TaskTagSuggestionItem(BaseModel):
    tag: str
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)


class TaskTagSuggestionResponse(BaseModel):
    suggestions: list[TaskTagSuggestionItem] = Field(default_factory=list)
    generated_at: datetime


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["low", "medium", "high"]


class TaskRead(BaseModel):
    id: str
    project_id: str
    title: str
    content: str
    tags: list[str]
    status: TaskStatus
    created_by: str
    analyst_id: str
    reviewer_analyst_id: str | None
    developer_id: str | None
    tester_id: str | None
    reviewer_approved_at: datetime | None = None
    validation_result: dict | None
    attachments: list[TaskAttachmentRead] = Field(default_factory=list)
    indexed_at: datetime | None = None
    embeddings_stale: bool
    requires_revalidation: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class ValidationResult(BaseModel):
    verdict: Literal["approved", "needs_rework"]
    issues: list[ValidationIssue]
    questions: list[str]
    validated_at: datetime
