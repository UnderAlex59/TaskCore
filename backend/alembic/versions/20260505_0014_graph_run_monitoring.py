"""Add LangGraph run monitoring tables.

Revision ID: 20260505_0014
Revises: 20260429_0013
Create Date: 2026-05-05 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260505_0014"
down_revision = "20260429_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graph_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("graph_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_preview", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_state_preview", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_graph_run_logs_started_at", "graph_run_logs", ["started_at"], unique=False)
    op.create_index("idx_graph_run_logs_graph_status", "graph_run_logs", ["graph_key", "status"], unique=False)
    op.create_index("idx_graph_run_logs_task_started", "graph_run_logs", ["task_id", "started_at"], unique=False)

    op.create_table(
        "graph_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("node_name", sa.String(length=255), nullable=True),
        sa.Column("namespace", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_run_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_graph_run_events_run_sequence", "graph_run_events", ["graph_run_id", "sequence"], unique=False)
    op.create_index("idx_graph_run_events_node", "graph_run_events", ["node_name"], unique=False)

    op.add_column("llm_request_logs", sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("llm_request_logs", sa.Column("graph_node_name", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_llm_request_logs_graph_run_id",
        "llm_request_logs",
        "graph_run_logs",
        ["graph_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_llm_request_logs_graph_run", "llm_request_logs", ["graph_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_llm_request_logs_graph_run", table_name="llm_request_logs")
    op.drop_constraint("fk_llm_request_logs_graph_run_id", "llm_request_logs", type_="foreignkey")
    op.drop_column("llm_request_logs", "graph_node_name")
    op.drop_column("llm_request_logs", "graph_run_id")
    op.drop_index("idx_graph_run_events_node", table_name="graph_run_events")
    op.drop_index("idx_graph_run_events_run_sequence", table_name="graph_run_events")
    op.drop_table("graph_run_events")
    op.drop_index("idx_graph_run_logs_task_started", table_name="graph_run_logs")
    op.drop_index("idx_graph_run_logs_graph_status", table_name="graph_run_logs")
    op.drop_index("idx_graph_run_logs_started_at", table_name="graph_run_logs")
    op.drop_table("graph_run_logs")
