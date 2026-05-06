"""Add graph monitoring runtime toggle.

Revision ID: 20260505_0015
Revises: 20260505_0014
Create Date: 2026-05-05 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0015"
down_revision = "20260505_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_runtime_settings",
        sa.Column(
            "graph_monitoring_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("llm_runtime_settings", "graph_monitoring_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_runtime_settings", "graph_monitoring_enabled")
