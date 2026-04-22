"""Track validation question source."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260421_0008"
down_revision = "20260417_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "validation_questions",
        sa.Column("source", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE validation_questions
        SET source = CASE
            WHEN validated_at IS NULL THEN 'chat'
            ELSE 'validation'
        END
        """
    )
    op.alter_column(
        "validation_questions",
        "source",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'chat'"),
    )
    op.create_index(
        "ix_validation_questions_source",
        "validation_questions",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_validation_questions_source", table_name="validation_questions")
    op.drop_column("validation_questions", "source")
