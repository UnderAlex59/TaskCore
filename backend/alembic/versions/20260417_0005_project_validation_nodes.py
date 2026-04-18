"""Add per-project validation node settings."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260417_0005"
down_revision = "20260416_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "validation_node_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                """'{"core_rules": true, "custom_rules": true, "context_questions": true}'::jsonb"""
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "validation_node_settings")
