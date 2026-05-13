"""Add RAG eval datasets and run history.

Revision ID: 20260512_0017
Revises: 20260507_0016
Create Date: 2026-05-12 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260512_0017"
down_revision = "20260507_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_eval_datasets",
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
        sa.UniqueConstraint("project_id", "name", name="uq_rag_eval_datasets_project_name"),
    )
    op.create_index("idx_rag_eval_datasets_project", "rag_eval_datasets", ["project_id"])

    op.create_table(
        "rag_eval_dataset_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=False),
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
        sa.ForeignKeyConstraint(["dataset_id"], ["rag_eval_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id", "external_id", name="uq_rag_eval_dataset_tasks_external_id"
        ),
        sa.UniqueConstraint("dataset_id", "task_id", name="uq_rag_eval_dataset_tasks_task_id"),
    )
    op.create_index("idx_rag_eval_dataset_tasks_dataset", "rag_eval_dataset_tasks", ["dataset_id"])
    op.create_index("idx_rag_eval_dataset_tasks_task", "rag_eval_dataset_tasks", ["task_id"])

    op.create_table(
        "rag_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("task_external_id", sa.String(length=255), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("expected_relevant", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["dataset_id"], ["rag_eval_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "external_id", name="uq_rag_eval_cases_external_id"),
    )
    op.create_index("idx_rag_eval_cases_dataset", "rag_eval_cases", ["dataset_id"])
    op.create_index("idx_rag_eval_cases_task", "rag_eval_cases", ["task_id"])

    op.create_table(
        "rag_eval_runs",
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
        sa.ForeignKeyConstraint(["dataset_id"], ["rag_eval_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rag_eval_runs_dataset_created", "rag_eval_runs", ["dataset_id", "created_at"]
    )
    op.create_index("idx_rag_eval_runs_status", "rag_eval_runs", ["status"])

    op.create_table(
        "rag_eval_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retrieved_chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched_expected", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judge_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("answer_latency_ms", sa.Integer(), nullable=True),
        sa.Column("judge_latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["rag_eval_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["rag_eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_rag_eval_case_results_run_case"),
    )
    op.create_index("idx_rag_eval_case_results_run", "rag_eval_case_results", ["run_id"])

    op.create_table(
        "rag_eval_index_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_external_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attachment_payload_ms", sa.Integer(), nullable=True),
        sa.Column("chunking_ms", sa.Integer(), nullable=True),
        sa.Column("embedding_and_qdrant_write_ms", sa.Integer(), nullable=True),
        sa.Column("qdrant_cleanup_ms", sa.Integer(), nullable=True),
        sa.Column("total_index_ms", sa.Integer(), nullable=True),
        sa.Column("chunks_total", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["rag_eval_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "task_id", name="uq_rag_eval_index_results_run_task"),
    )
    op.create_index("idx_rag_eval_index_results_run", "rag_eval_index_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("idx_rag_eval_index_results_run", table_name="rag_eval_index_results")
    op.drop_table("rag_eval_index_results")
    op.drop_index("idx_rag_eval_case_results_run", table_name="rag_eval_case_results")
    op.drop_table("rag_eval_case_results")
    op.drop_index("idx_rag_eval_runs_status", table_name="rag_eval_runs")
    op.drop_index("idx_rag_eval_runs_dataset_created", table_name="rag_eval_runs")
    op.drop_table("rag_eval_runs")
    op.drop_index("idx_rag_eval_cases_task", table_name="rag_eval_cases")
    op.drop_index("idx_rag_eval_cases_dataset", table_name="rag_eval_cases")
    op.drop_table("rag_eval_cases")
    op.drop_index("idx_rag_eval_dataset_tasks_task", table_name="rag_eval_dataset_tasks")
    op.drop_index("idx_rag_eval_dataset_tasks_dataset", table_name="rag_eval_dataset_tasks")
    op.drop_table("rag_eval_dataset_tasks")
    op.drop_index("idx_rag_eval_datasets_project", table_name="rag_eval_datasets")
    op.drop_table("rag_eval_datasets")
