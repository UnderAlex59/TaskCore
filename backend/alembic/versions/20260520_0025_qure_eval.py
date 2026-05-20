"""Add QuRE eval admin tool tables.

Revision ID: 20260520_0025
Revises: 20260518_0024
Create Date: 2026-05-20 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260520_0025"
down_revision = "20260518_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qure_eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_limit", sa.Integer(), nullable=False),
        sa.Column("selection_strategy", sa.String(length=100), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("selected_rows", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_qure_eval_runs_project", "qure_eval_runs", ["project_id"])
    op.create_index("idx_qure_eval_runs_status", "qure_eval_runs", ["status"])
    op.create_index(
        "idx_qure_eval_runs_created",
        "qure_eval_runs",
        ["created_at"],
    )

    op.create_table(
        "qure_eval_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("judge_graph_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("defect", sa.String(length=32), nullable=False),
        sa.Column("weak_word", sa.String(length=255), nullable=False),
        sa.Column("expected_verdict", sa.String(length=32), nullable=False),
        sa.Column("actual_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("judge_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["judge_graph_run_id"],
            ["graph_run_logs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["qure_eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_qure_eval_case_results_run",
        "qure_eval_case_results",
        ["run_id"],
    )
    op.create_index(
        "idx_qure_eval_case_results_graph_run",
        "qure_eval_case_results",
        ["graph_run_id"],
    )
    op.create_index(
        "idx_qure_eval_case_results_judge_graph_run",
        "qure_eval_case_results",
        ["judge_graph_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_qure_eval_case_results_judge_graph_run",
        table_name="qure_eval_case_results",
    )
    op.drop_index(
        "idx_qure_eval_case_results_graph_run",
        table_name="qure_eval_case_results",
    )
    op.drop_index("idx_qure_eval_case_results_run", table_name="qure_eval_case_results")
    op.drop_table("qure_eval_case_results")
    op.drop_index("idx_qure_eval_runs_created", table_name="qure_eval_runs")
    op.drop_index("idx_qure_eval_runs_status", table_name="qure_eval_runs")
    op.drop_index("idx_qure_eval_runs_project", table_name="qure_eval_runs")
    op.drop_table("qure_eval_runs")
