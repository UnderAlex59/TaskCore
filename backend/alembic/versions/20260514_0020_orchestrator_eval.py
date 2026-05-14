"""Add orchestrator eval datasets and run history.

Revision ID: 20260514_0020
Revises: 20260513_0019
Create Date: 2026-05-14 18:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260514_0020"
down_revision = "20260513_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_eval_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_orchestrator_eval_datasets_project_name",
        ),
    )
    op.create_index(
        "idx_orchestrator_eval_datasets_project",
        "orchestrator_eval_datasets",
        ["project_id"],
    )

    op.create_table(
        "orchestrator_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("task_title", sa.String(length=500), nullable=False),
        sa.Column("task_status", sa.String(length=64), nullable=False),
        sa.Column("task_content", sa.Text(), nullable=False),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("message_content", sa.Text(), nullable=False),
        sa.Column("requested_agent", sa.String(length=100), nullable=True),
        sa.Column("expected_route", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["orchestrator_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "external_id",
            name="uq_orchestrator_eval_cases_external_id",
        ),
    )
    op.create_index(
        "idx_orchestrator_eval_cases_dataset",
        "orchestrator_eval_cases",
        ["dataset_id"],
    )
    op.create_index(
        "idx_orchestrator_eval_cases_project",
        "orchestrator_eval_cases",
        ["project_id"],
    )
    op.create_index("idx_orchestrator_eval_cases_task", "orchestrator_eval_cases", ["task_id"])

    op.create_table(
        "orchestrator_eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["orchestrator_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_orchestrator_eval_runs_dataset_created",
        "orchestrator_eval_runs",
        ["dataset_id", "created_at"],
    )
    op.create_index("idx_orchestrator_eval_runs_status", "orchestrator_eval_runs", ["status"])

    op.create_table(
        "orchestrator_eval_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_route", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actual_route", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["orchestrator_eval_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["orchestrator_eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_orchestrator_eval_case_results_run_case"),
    )
    op.create_index(
        "idx_orchestrator_eval_case_results_run",
        "orchestrator_eval_case_results",
        ["run_id"],
    )
    op.create_index(
        "idx_orchestrator_eval_case_results_graph_run",
        "orchestrator_eval_case_results",
        ["graph_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_orchestrator_eval_case_results_graph_run",
        table_name="orchestrator_eval_case_results",
    )
    op.drop_index(
        "idx_orchestrator_eval_case_results_run",
        table_name="orchestrator_eval_case_results",
    )
    op.drop_table("orchestrator_eval_case_results")
    op.drop_index("idx_orchestrator_eval_runs_status", table_name="orchestrator_eval_runs")
    op.drop_index(
        "idx_orchestrator_eval_runs_dataset_created",
        table_name="orchestrator_eval_runs",
    )
    op.drop_table("orchestrator_eval_runs")
    op.drop_index("idx_orchestrator_eval_cases_task", table_name="orchestrator_eval_cases")
    op.drop_index("idx_orchestrator_eval_cases_project", table_name="orchestrator_eval_cases")
    op.drop_index("idx_orchestrator_eval_cases_dataset", table_name="orchestrator_eval_cases")
    op.drop_table("orchestrator_eval_cases")
    op.drop_index(
        "idx_orchestrator_eval_datasets_project",
        table_name="orchestrator_eval_datasets",
    )
    op.drop_table("orchestrator_eval_datasets")
