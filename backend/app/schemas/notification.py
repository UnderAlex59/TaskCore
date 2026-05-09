from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    id: str
    user_id: str
    type: str
    priority: str
    title: str
    body: str
    project_id: str | None
    task_id: str | None
    message_id: str | None
    metadata: dict | None
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationPageRead(BaseModel):
    items: list[NotificationRead]
    unread_count: int


class ChatUnreadRead(BaseModel):
    task_id: str
    unread_count: int
    last_read_at: datetime | None


class NotificationSettingsRead(BaseModel):
    telegram_important_enabled: bool = True
    telegram_normal_enabled: bool = True
    telegram_linked: bool = False
    telegram_username: str | None = None


class NotificationSettingsUpdate(BaseModel):
    telegram_important_enabled: bool | None = None
    telegram_normal_enabled: bool | None = None


class TelegramLinkTokenRead(BaseModel):
    token: str = Field(description="Одноразовый код для привязки Telegram-бота")
    expires_at: datetime
    deep_link: str | None = Field(
        default=None,
        description="Ссылка для запуска Telegram-бота с payload привязки",
    )


class TelegramWebhookResponse(BaseModel):
    ok: bool
    message: str
