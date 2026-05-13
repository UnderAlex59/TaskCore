"""Allow task and project deletion with notifications.

Revision ID: 20260513_0019
Revises: 20260512_0018
Create Date: 2026-05-13 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260513_0019"
down_revision = "20260512_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_notifications_message_id_messages",
        "notifications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notifications_task_id_tasks",
        "notifications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notifications_project_id_projects",
        "notifications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_notifications_project_id_projects",
        "notifications",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_notifications_task_id_tasks",
        "notifications",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_notifications_message_id_messages",
        "notifications",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notifications_message_id_messages",
        "notifications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notifications_task_id_tasks",
        "notifications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_notifications_project_id_projects",
        "notifications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_notifications_project_id_projects",
        "notifications",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_notifications_task_id_tasks",
        "notifications",
        "tasks",
        ["task_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_notifications_message_id_messages",
        "notifications",
        "messages",
        ["message_id"],
        ["id"],
    )
