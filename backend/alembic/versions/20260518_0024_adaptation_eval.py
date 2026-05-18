"""Add adaptation eval lab tables.

Revision ID: 20260518_0024
Revises: 20260516_0023
Create Date: 2026-05-18 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260518_0024"
down_revision = "20260516_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adaptation_eval_datasets",
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
            name="uq_adaptation_eval_datasets_project_name",
        ),
    )
    op.create_index(
        "idx_adaptation_eval_datasets_project",
        "adaptation_eval_datasets",
        ["project_id"],
    )

    op.create_table(
        "adaptation_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("scenario_type", sa.String(length=100), nullable=False),
        sa.Column("historical_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("probe_task", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "expected_captured_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "expected_retrieved_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "expected_context_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expected_verdict", sa.String(length=32), nullable=False),
        sa.Column(
            "expected_context_issues",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["adaptation_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "external_id",
            name="uq_adaptation_eval_cases_external_id",
        ),
    )
    op.create_index(
        "idx_adaptation_eval_cases_dataset",
        "adaptation_eval_cases",
        ["dataset_id"],
    )

    op.create_table(
        "adaptation_eval_runs",
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
            ["adaptation_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_adaptation_eval_runs_dataset_created",
        "adaptation_eval_runs",
        ["dataset_id", "created_at"],
    )
    op.create_index("idx_adaptation_eval_runs_status", "adaptation_eval_runs", ["status"])

    op.create_table(
        "adaptation_eval_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("core_graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("full_graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("synthetic_task_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actual_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diffs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["adaptation_eval_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["core_graph_run_id"],
            ["graph_run_logs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["full_graph_run_id"],
            ["graph_run_logs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["adaptation_eval_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "case_id",
            name="uq_adaptation_eval_case_results_run_case",
        ),
    )
    op.create_index(
        "idx_adaptation_eval_case_results_run",
        "adaptation_eval_case_results",
        ["run_id"],
    )
    op.create_index(
        "idx_adaptation_eval_case_results_case",
        "adaptation_eval_case_results",
        ["case_id"],
    )
    op.create_index(
        "idx_adaptation_eval_case_results_core_graph_run",
        "adaptation_eval_case_results",
        ["core_graph_run_id"],
    )
    op.create_index(
        "idx_adaptation_eval_case_results_full_graph_run",
        "adaptation_eval_case_results",
        ["full_graph_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_adaptation_eval_case_results_full_graph_run",
        table_name="adaptation_eval_case_results",
    )
    op.drop_index(
        "idx_adaptation_eval_case_results_core_graph_run",
        table_name="adaptation_eval_case_results",
    )
    op.drop_index(
        "idx_adaptation_eval_case_results_case",
        table_name="adaptation_eval_case_results",
    )
    op.drop_index(
        "idx_adaptation_eval_case_results_run",
        table_name="adaptation_eval_case_results",
    )
    op.drop_table("adaptation_eval_case_results")
    op.drop_index("idx_adaptation_eval_runs_status", table_name="adaptation_eval_runs")
    op.drop_index(
        "idx_adaptation_eval_runs_dataset_created",
        table_name="adaptation_eval_runs",
    )
    op.drop_table("adaptation_eval_runs")
    op.drop_index("idx_adaptation_eval_cases_dataset", table_name="adaptation_eval_cases")
    op.drop_table("adaptation_eval_cases")
    op.drop_index(
        "idx_adaptation_eval_datasets_project",
        table_name="adaptation_eval_datasets",
    )
    op.drop_table("adaptation_eval_datasets")
