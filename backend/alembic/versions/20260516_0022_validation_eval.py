"""Add validation eval lab tables.

Revision ID: 20260516_0022
Revises: 20260514_0021
Create Date: 2026-05-16 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260516_0022"
down_revision = "20260514_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_eval_datasets",
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
            name="uq_validation_eval_datasets_project_name",
        ),
    )
    op.create_index(
        "idx_validation_eval_datasets_project",
        "validation_eval_datasets",
        ["project_id"],
    )

    op.create_table(
        "validation_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("attachment_names", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("custom_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("related_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "historical_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expected_verdict", sa.String(length=32), nullable=False),
        sa.Column("expected_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "expected_questions",
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
            ["validation_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "external_id",
            name="uq_validation_eval_cases_external_id",
        ),
    )
    op.create_index(
        "idx_validation_eval_cases_dataset",
        "validation_eval_cases",
        ["dataset_id"],
    )

    op.create_table(
        "validation_eval_runs",
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
            ["validation_eval_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_validation_eval_runs_dataset_created",
        "validation_eval_runs",
        ["dataset_id", "created_at"],
    )
    op.create_index("idx_validation_eval_runs_status", "validation_eval_runs", ["status"])

    op.create_table(
        "validation_eval_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("judge_graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("variant_key", sa.String(length=100), nullable=False),
        sa.Column("variant_label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actual_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diffs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("judge_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["validation_eval_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["judge_graph_run_id"],
            ["graph_run_logs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["validation_eval_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "case_id",
            "variant_key",
            name="uq_validation_eval_case_results_run_case_variant",
        ),
    )
    op.create_index(
        "idx_validation_eval_case_results_run",
        "validation_eval_case_results",
        ["run_id"],
    )
    op.create_index(
        "idx_validation_eval_case_results_case",
        "validation_eval_case_results",
        ["case_id"],
    )
    op.create_index(
        "idx_validation_eval_case_results_graph_run",
        "validation_eval_case_results",
        ["graph_run_id"],
    )
    op.create_index(
        "idx_validation_eval_case_results_judge_graph_run",
        "validation_eval_case_results",
        ["judge_graph_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_validation_eval_case_results_judge_graph_run",
        table_name="validation_eval_case_results",
    )
    op.drop_index(
        "idx_validation_eval_case_results_graph_run",
        table_name="validation_eval_case_results",
    )
    op.drop_index(
        "idx_validation_eval_case_results_case",
        table_name="validation_eval_case_results",
    )
    op.drop_index(
        "idx_validation_eval_case_results_run",
        table_name="validation_eval_case_results",
    )
    op.drop_table("validation_eval_case_results")
    op.drop_index("idx_validation_eval_runs_status", table_name="validation_eval_runs")
    op.drop_index(
        "idx_validation_eval_runs_dataset_created",
        table_name="validation_eval_runs",
    )
    op.drop_table("validation_eval_runs")
    op.drop_index("idx_validation_eval_cases_dataset", table_name="validation_eval_cases")
    op.drop_table("validation_eval_cases")
    op.drop_index("idx_validation_eval_datasets_project", table_name="validation_eval_datasets")
    op.drop_table("validation_eval_datasets")
