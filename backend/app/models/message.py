from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessageType(str, enum.Enum):
    GENERAL = "general"
    QUESTION = "question"
    CHANGE_PROPOSAL = "change_proposal"
    AGENT_ANSWER = "agent_answer"
    AGENT_PROPOSAL = "agent_proposal"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message_type: Mapped[MessageType] = mapped_column(
        SAEnum(MessageType, name="message_type", values_callable=lambda items: [item.value for item in items]),
        nullable=False,
        default=MessageType.GENERAL,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
