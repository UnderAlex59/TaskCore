"""Add validation questions table for admin review."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260417_0007"
down_revision = "20260417_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_questions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("validation_verdict", sa.String(length=32), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_questions")),
    )
    op.create_index(
        op.f("ix_validation_questions_task_id"),
        "validation_questions",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_validation_questions_validated_at",
        "validation_questions",
        ["validated_at"],
        unique=False,
    )
    op.create_index(
        "ix_validation_questions_validation_verdict",
        "validation_questions",
        ["validation_verdict"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_validation_questions_validation_verdict", table_name="validation_questions")
    op.drop_index("ix_validation_questions_validated_at", table_name="validation_questions")
    op.drop_index(op.f("ix_validation_questions_task_id"), table_name="validation_questions")
    op.drop_table("validation_questions")
