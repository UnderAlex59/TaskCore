from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMAgentPromptVersion(Base):
    __tablename__ = "llm_agent_prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "prompt_key",
            "revision",
            name="uq_llm_agent_prompt_versions_revision",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    prompt_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
