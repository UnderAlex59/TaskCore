from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not any(char.isupper() for char in value):
            raise ValueError("Пароль должен содержать хотя бы одну заглавную букву")
        if not any(char.isdigit() for char in value):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    nickname: str | None
    avatar_url: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class SessionRead(BaseModel):
    id: str
    family_id: str
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    revoked: bool

    @field_validator("ip_address", mode="before")
    @classmethod
    def normalize_ip_address(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    model_config = ConfigDict(from_attributes=True)
