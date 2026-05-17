from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ValidationEvalDataset(Base):
    __tablename__ = "validation_eval_datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_validation_eval_datasets_project_name"),
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


class ValidationEvalCase(Base):
    __tablename__ = "validation_eval_cases"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id", name="uq_validation_eval_cases_external_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("validation_eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    attachment_names: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    custom_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    related_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    historical_questions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    expected_verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    expected_questions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    expected_context_questions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    case_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ValidationEvalRun(Base):
    __tablename__ = "validation_eval_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("validation_eval_datasets.id", ondelete="CASCADE"),
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


class ValidationEvalCaseResult(Base):
    __tablename__ = "validation_eval_case_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_id",
            "variant_key",
            name="uq_validation_eval_case_results_run_case_variant",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("validation_eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("validation_eval_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    graph_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("graph_run_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    judge_graph_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("graph_run_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    variant_key: Mapped[str] = mapped_column(String(100), nullable=False)
    variant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actual_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    diffs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    judge_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
