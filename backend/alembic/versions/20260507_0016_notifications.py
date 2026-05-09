"""Add notifications and Telegram linking.

Revision ID: 20260507_0016
Revises: 20260505_0015
Create Date: 2026-05-07 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260507_0016"
down_revision = "20260505_0015"
branch_labels = None
depends_on = None


notification_type = postgresql.ENUM(
    "qa_needs_analyst",
    "analyst_requested",
    "task_assigned",
    "task_status_changed",
    "chat_mention",
    name="notification_type",
    create_type=False,
)
notification_priority = postgresql.ENUM(
    "normal",
    "important",
    name="notification_priority",
    create_type=False,
)
notification_delivery_channel = postgresql.ENUM(
    "in_app",
    "telegram",
    name="notification_delivery_channel",
    create_type=False,
)
notification_delivery_status = postgresql.ENUM(
    "pending",
    "sent",
    "failed",
    "skipped",
    name="notification_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    notification_type.create(bind, checkfirst=True)
    notification_priority.create(bind, checkfirst=True)
    notification_delivery_channel.create(bind, checkfirst=True)
    notification_delivery_status.create(bind, checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "notification_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                """'{"telegram_important_enabled": true, "telegram_normal_enabled": true}'::jsonb"""
            ),
        ),
    )
    op.alter_column("users", "notification_settings", server_default=None)

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("priority", notification_priority, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifications_user_read",
        "notifications",
        ["user_id", "read_at"],
        unique=False,
    )
    op.create_index(
        "idx_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_notifications_dedupe",
        "notifications",
        ["user_id", "dedupe_key"],
        unique=False,
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel", notification_delivery_channel, nullable=False),
        sa.Column("status", notification_delivery_status, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notification_deliveries_notification_id"),
        "notification_deliveries",
        ["notification_id"],
        unique=False,
    )

    op.create_table(
        "telegram_connections",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=64), nullable=True),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_telegram_connections_user_id"),
        "telegram_connections",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_telegram_link_tokens_user_id"),
        "telegram_link_tokens",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "chat_read_states",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "user_id", name="uq_chat_read_states_task_user"),
    )
    op.create_index(
        op.f("ix_chat_read_states_task_id"),
        "chat_read_states",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_read_states_user_id"),
        "chat_read_states",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_read_states_user_id"), table_name="chat_read_states")
    op.drop_index(op.f("ix_chat_read_states_task_id"), table_name="chat_read_states")
    op.drop_table("chat_read_states")
    op.drop_index(op.f("ix_telegram_link_tokens_user_id"), table_name="telegram_link_tokens")
    op.drop_table("telegram_link_tokens")
    op.drop_index(op.f("ix_telegram_connections_user_id"), table_name="telegram_connections")
    op.drop_table("telegram_connections")
    op.drop_index(
        op.f("ix_notification_deliveries_notification_id"),
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
    op.drop_index("idx_notifications_dedupe", table_name="notifications")
    op.drop_index("idx_notifications_user_created", table_name="notifications")
    op.drop_index("idx_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("users", "notification_settings")

    notification_delivery_status.drop(op.get_bind(), checkfirst=True)
    notification_delivery_channel.drop(op.get_bind(), checkfirst=True)
    notification_priority.drop(op.get_bind(), checkfirst=True)
    notification_type.drop(op.get_bind(), checkfirst=True)
