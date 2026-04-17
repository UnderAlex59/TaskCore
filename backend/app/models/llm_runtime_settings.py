from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMRuntimeSettings(Base):
    __tablename__ = "llm_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_provider_config_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_log_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="metadata_only")
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
