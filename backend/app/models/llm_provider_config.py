from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=0.2)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    masked_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_cost_per_1k_tokens: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    output_cost_per_1k_tokens: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    vision_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vision_system_prompt_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="system_role",
    )
    vision_message_order: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="text_first",
    )
    vision_detail: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="default",
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
