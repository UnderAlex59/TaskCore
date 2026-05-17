"""Add expected context questions to validation eval cases.

Revision ID: 20260516_0023
Revises: 20260516_0022
Create Date: 2026-05-16 00:23:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260516_0023"
down_revision = "20260516_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "validation_eval_cases",
        sa.Column(
            "expected_context_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column(
        "validation_eval_cases",
        "expected_context_questions",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("validation_eval_cases", "expected_context_questions")
