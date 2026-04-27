"""Add vision settings to LLM provider configs."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260426_0011"
down_revision = "20260422_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_provider_configs",
        sa.Column(
            "vision_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "llm_provider_configs",
        sa.Column(
            "vision_system_prompt_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'system_role'"),
        ),
    )
    op.add_column(
        "llm_provider_configs",
        sa.Column(
            "vision_message_order",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'text_first'"),
        ),
    )
    op.add_column(
        "llm_provider_configs",
        sa.Column(
            "vision_detail",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_provider_configs", "vision_detail")
    op.drop_column("llm_provider_configs", "vision_message_order")
    op.drop_column("llm_provider_configs", "vision_system_prompt_mode")
    op.drop_column("llm_provider_configs", "vision_enabled")
