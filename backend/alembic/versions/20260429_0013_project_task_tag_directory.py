"""project task tag directory

Revision ID: 20260429_0013
Revises: 20260429_0012
Create Date: 2026-04-29 18:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260429_0013"
down_revision = "20260429_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_task_tags",
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_tag_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_tag_id"], ["task_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "task_tag_id"),
    )
    op.create_index(
        "ix_project_task_tags_task_tag_id",
        "project_task_tags",
        ["task_tag_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO project_task_tags (project_id, task_tag_id, created_by)
        SELECT DISTINCT task.project_id, tag.id, COALESCE(project.created_by, task.created_by)
        FROM tasks AS task
        JOIN task_tags AS tag
          ON tag.name = ANY(task.tags)
        JOIN projects AS project
          ON project.id = task.project_id
        """
    )
    op.execute(
        """
        INSERT INTO project_task_tags (project_id, task_tag_id, created_by)
        SELECT DISTINCT rule.project_id, tag.id, COALESCE(project.created_by, rule.created_by)
        FROM custom_rules AS rule
        JOIN LATERAL unnest(rule.applies_to_tags) AS applied_tag(name) ON TRUE
        JOIN task_tags AS tag
          ON tag.name = applied_tag.name
        JOIN projects AS project
          ON project.id = rule.project_id
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_task_tags_task_tag_id", table_name="project_task_tags")
    op.drop_table("project_task_tags")
