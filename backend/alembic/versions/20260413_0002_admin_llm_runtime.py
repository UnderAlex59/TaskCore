"""Add admin LLM runtime, telemetry, and audit tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260413_0002"
down_revision = "20260409_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_kind", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("temperature", sa.Numeric(4, 2), nullable=False, server_default=sa.text("0.2")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("masked_secret", sa.String(length=64), nullable=True),
        sa.Column("input_cost_per_1k_tokens", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_cost_per_1k_tokens", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "idx_llm_provider_configs_enabled",
        "llm_provider_configs",
        ["enabled", "provider_kind"],
    )

    op.create_table(
        "llm_runtime_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "default_provider_config_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "prompt_log_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'metadata_only'"),
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "llm_agent_overrides",
        sa.Column("agent_key", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column(
            "provider_config_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("llm_provider_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_llm_agent_overrides_provider",
        "llm_agent_overrides",
        ["provider_config_id", "enabled"],
    )

    op.create_table(
        "llm_request_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("request_kind", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("agent_key", sa.String(length=100), nullable=True),
        sa.Column(
            "provider_config_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_kind", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_llm_request_logs_created_at", "llm_request_logs", ["created_at"])
    op.create_index(
        "idx_llm_request_logs_provider_status",
        "llm_request_logs",
        ["provider_kind", "status", "created_at"],
    )
    op.create_index(
        "idx_llm_request_logs_actor_created_at",
        "llm_request_logs",
        ["actor_user_id", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("idx_audit_events_actor_created_at", "audit_events", ["actor_user_id", "created_at"])
    op.create_index("idx_audit_events_event_type_created_at", "audit_events", ["event_type", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_events_event_type_created_at", table_name="audit_events")
    op.drop_index("idx_audit_events_actor_created_at", table_name="audit_events")
    op.drop_index("idx_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("idx_llm_request_logs_actor_created_at", table_name="llm_request_logs")
    op.drop_index("idx_llm_request_logs_provider_status", table_name="llm_request_logs")
    op.drop_index("idx_llm_request_logs_created_at", table_name="llm_request_logs")
    op.drop_table("llm_request_logs")

    op.drop_index("idx_llm_agent_overrides_provider", table_name="llm_agent_overrides")
    op.drop_table("llm_agent_overrides")

    op.drop_table("llm_runtime_settings")

    op.drop_index("idx_llm_provider_configs_enabled", table_name="llm_provider_configs")
    op.drop_table("llm_provider_configs")
