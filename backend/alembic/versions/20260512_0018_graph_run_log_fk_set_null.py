"""Allow project and task deletion with graph run logs.

Revision ID: 20260512_0018
Revises: 20260512_0017
Create Date: 2026-05-12 13:30:00
"""

from __future__ import annotations

from alembic import op

revision = "20260512_0018"
down_revision = "20260512_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_graph_run_logs_project_id_projects",
        "graph_run_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_graph_run_logs_task_id_tasks",
        "graph_run_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_graph_run_logs_project_id_projects",
        "graph_run_logs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_graph_run_logs_task_id_tasks",
        "graph_run_logs",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_graph_run_logs_task_id_tasks",
        "graph_run_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_graph_run_logs_project_id_projects",
        "graph_run_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_graph_run_logs_task_id_tasks",
        "graph_run_logs",
        "tasks",
        ["task_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_graph_run_logs_project_id_projects",
        "graph_run_logs",
        "projects",
        ["project_id"],
        ["id"],
    )
