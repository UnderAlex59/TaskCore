"""Add second analyst review and testing workflow statuses."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260429_0012"
down_revision = "20260426_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'ready_for_testing'")
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'testing'")

    op.add_column("tasks", sa.Column("reviewer_analyst_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("tasks", sa.Column("reviewer_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_tasks_reviewer_analyst_id_users",
        "tasks",
        "users",
        ["reviewer_analyst_id"],
        ["id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    legacy_task_status = postgresql.ENUM(
        "draft",
        "validating",
        "needs_rework",
        "awaiting_approval",
        "ready_for_dev",
        "in_progress",
        "done",
        name="task_status_legacy",
    )

    op.drop_constraint("fk_tasks_reviewer_analyst_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "reviewer_approved_at")
    op.drop_column("tasks", "reviewer_analyst_id")

    op.execute("UPDATE tasks SET status = 'in_progress' WHERE status = 'ready_for_testing'")
    op.execute("UPDATE tasks SET status = 'done' WHERE status = 'testing'")

    legacy_task_status.create(bind, checkfirst=True)
    op.execute("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status TYPE task_status_legacy USING status::text::task_status_legacy"
    )
    op.execute("DROP TYPE task_status")
    op.execute("ALTER TYPE task_status_legacy RENAME TO task_status")
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'draft'")
