"""Add user account deletion marker.

Revision ID: 20260514_0021
Revises: 20260514_0020
Create Date: 2026-05-14 22:15:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260514_0021"
down_revision = "20260514_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")
