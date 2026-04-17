from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import UserRole


class UserSummary(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    nickname: str | None
    avatar_url: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None

    model_config = ConfigDict(use_enum_values=True)


class UserProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=2, max_length=100)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=100)
    remove_avatar: bool = False

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not any(char.isupper() for char in value):
            raise ValueError("Пароль должен содержать хотя бы одну заглавную букву")
        if not any(char.isdigit() for char in value):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        return value

    @model_validator(mode="after")
    def validate_password_update(self) -> "UserProfileUpdate":
        if self.new_password is not None and not self.current_password:
            raise ValueError("Для смены пароля нужно указать текущий пароль")
        return self
