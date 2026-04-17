"""Replace single assignee with task team and approval stage."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260416_0004"
down_revision = "20260415_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'awaiting_approval'")

    op.add_column("tasks", sa.Column("analyst_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("tasks", sa.Column("developer_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("tasks", sa.Column("tester_id", postgresql.UUID(as_uuid=False), nullable=True))

    op.create_foreign_key("fk_tasks_analyst_id_users", "tasks", "users", ["analyst_id"], ["id"])
    op.create_foreign_key("fk_tasks_developer_id_users", "tasks", "users", ["developer_id"], ["id"])
    op.create_foreign_key("fk_tasks_tester_id_users", "tasks", "users", ["tester_id"], ["id"])

    op.execute("UPDATE tasks SET analyst_id = created_by WHERE analyst_id IS NULL")
    op.execute(
        """
        UPDATE tasks AS task
        SET developer_id = task.assigned_to
        FROM project_members AS member
        WHERE member.project_id = task.project_id
          AND member.user_id = task.assigned_to
          AND member.role = 'DEVELOPER'
        """
    )
    op.execute(
        """
        UPDATE tasks AS task
        SET tester_id = task.assigned_to
        FROM project_members AS member
        WHERE member.project_id = task.project_id
          AND member.user_id = task.assigned_to
          AND member.role = 'TESTER'
        """
    )
    op.alter_column("tasks", "analyst_id", nullable=False)
    op.drop_column("tasks", "assigned_to")


def downgrade() -> None:
    bind = op.get_bind()
    legacy_task_status = postgresql.ENUM(
        "draft",
        "validating",
        "needs_rework",
        "ready_for_dev",
        "in_progress",
        "done",
        name="task_status_legacy",
    )

    op.add_column("tasks", sa.Column("assigned_to", postgresql.UUID(as_uuid=False), nullable=True))
    op.execute("UPDATE tasks SET assigned_to = COALESCE(developer_id, tester_id)")
    op.execute("UPDATE tasks SET status = 'ready_for_dev' WHERE status = 'awaiting_approval'")

    op.drop_constraint("fk_tasks_tester_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_developer_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_analyst_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "tester_id")
    op.drop_column("tasks", "developer_id")
    op.drop_column("tasks", "analyst_id")

    legacy_task_status.create(bind, checkfirst=True)
    op.execute("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status TYPE task_status_legacy USING status::text::task_status_legacy"
    )
    op.execute("DROP TYPE task_status")
    op.execute("ALTER TYPE task_status_legacy RENAME TO task_status")
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'draft'")
