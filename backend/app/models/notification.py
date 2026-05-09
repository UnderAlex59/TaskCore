from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationType(StrEnum):
    QA_NEEDS_ANALYST = "qa_needs_analyst"
    ANALYST_REQUESTED = "analyst_requested"
    TASK_ASSIGNED = "task_assigned"
    TASK_STATUS_CHANGED = "task_status_changed"
    CHAT_MENTION = "chat_mention"


class NotificationPriority(StrEnum):
    NORMAL = "normal"
    IMPORTANT = "important"


class NotificationDeliveryChannel(StrEnum):
    IN_APP = "in_app"
    TELEGRAM = "telegram"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(
            NotificationType,
            name="notification_type",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        SAEnum(
            NotificationPriority,
            name="notification_priority",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=NotificationPriority.NORMAL,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("projects.id"),
        nullable=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id"),
        nullable=True,
    )
    message_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("messages.id"),
        nullable=True,
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    notification_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[NotificationDeliveryChannel] = mapped_column(
        SAEnum(
            NotificationDeliveryChannel,
            name="notification_delivery_channel",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
    )
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        SAEnum(
            NotificationDeliveryStatus,
            name="notification_delivery_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=NotificationDeliveryStatus.PENDING,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramConnection(Base):
    __tablename__ = "telegram_connections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    telegram_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatReadState(Base):
    __tablename__ = "chat_read_states"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_chat_read_states_task_user"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
