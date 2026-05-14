from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrchestratorEvalDataset(Base):
    __tablename__ = "orchestrator_eval_datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_orchestrator_eval_datasets_project_name"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrchestratorEvalCase(Base):
    __tablename__ = "orchestrator_eval_cases"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "external_id",
            name="uq_orchestrator_eval_cases_external_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("orchestrator_eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_title: Mapped[str] = mapped_column(String(500), nullable=False)
    task_status: Mapped[str] = mapped_column(String(64), nullable=False)
    task_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    requested_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_route: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrchestratorEvalRun(Base):
    __tablename__ = "orchestrator_eval_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("orchestrator_eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrchestratorEvalCaseResult(Base):
    __tablename__ = "orchestrator_eval_case_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_orchestrator_eval_case_results_run_case"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("orchestrator_eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("orchestrator_eval_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    graph_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("graph_run_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_route: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actual_route: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
