"""Add editable LLM agent prompt configs."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260422_0010"
down_revision = "20260422_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_agent_prompt_configs",
        sa.Column("prompt_key", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_llm_agent_prompt_configs_agent_key",
        "llm_agent_prompt_configs",
        ["agent_key"],
    )

    op.create_table(
        "llm_agent_prompt_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("prompt_key", sa.String(length=120), nullable=False),
        sa.Column("agent_key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "prompt_key",
            "revision",
            name="uq_llm_agent_prompt_versions_revision",
        ),
    )
    op.create_index(
        "ix_llm_agent_prompt_versions_prompt_key",
        "llm_agent_prompt_versions",
        ["prompt_key"],
    )
    op.create_index(
        "ix_llm_agent_prompt_versions_agent_key",
        "llm_agent_prompt_versions",
        ["agent_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_agent_prompt_versions_agent_key",
        table_name="llm_agent_prompt_versions",
    )
    op.drop_index(
        "ix_llm_agent_prompt_versions_prompt_key",
        table_name="llm_agent_prompt_versions",
    )
    op.drop_table("llm_agent_prompt_versions")

    op.drop_index(
        "ix_llm_agent_prompt_configs_agent_key",
        table_name="llm_agent_prompt_configs",
    )
    op.drop_table("llm_agent_prompt_configs")
