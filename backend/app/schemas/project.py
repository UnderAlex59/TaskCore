from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class ProjectCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberCreate(BaseModel):
    user_id: str
    role: UserRole

    model_config = ConfigDict(use_enum_values=True)


class ProjectMemberRead(BaseModel):
    project_id: str
    user_id: str
    role: UserRole
    joined_at: datetime
    full_name: str
    email: EmailStr
    global_role: UserRole

    model_config = ConfigDict(use_enum_values=True)


class CustomRuleCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=5)
    applies_to_tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class CustomRuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=5)
    applies_to_tags: list[str] | None = None
    is_active: bool | None = None


class CustomRuleRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    applies_to_tags: list[str]
    is_active: bool
    created_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
