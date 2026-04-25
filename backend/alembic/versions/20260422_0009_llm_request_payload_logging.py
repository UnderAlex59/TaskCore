"""Add payload logging for LLM request monitoring."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260422_0009"
down_revision = "20260421_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_request_logs",
        sa.Column(
            "request_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column("llm_request_logs", sa.Column("response_text", sa.Text(), nullable=True))
    op.alter_column(
        "llm_runtime_settings",
        "prompt_log_mode",
        server_default=sa.text("'full'"),
    )
    op.execute(
        """
        UPDATE llm_runtime_settings
        SET prompt_log_mode = 'full'
        WHERE prompt_log_mode = 'metadata_only'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE llm_runtime_settings
        SET prompt_log_mode = 'metadata_only'
        WHERE prompt_log_mode = 'full'
        """
    )
    op.alter_column(
        "llm_runtime_settings",
        "prompt_log_mode",
        server_default=sa.text("'metadata_only'"),
    )
    op.drop_column("llm_request_logs", "response_text")
    op.drop_column("llm_request_logs", "request_messages")
