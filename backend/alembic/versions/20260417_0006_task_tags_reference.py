"""Add task tag reference catalog."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260417_0006"
down_revision = "20260417_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "task_tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("normalized_name", name="uq_task_tags_normalized_name"),
    )
    op.create_index("idx_task_tags_name", "task_tags", ["name"])

    op.execute(
        "CREATE TRIGGER trg_task_tags_updated_at BEFORE UPDATE ON task_tags "
        "FOR EACH ROW EXECUTE FUNCTION update_updated_at()"
    )

    actor_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM users
            ORDER BY CASE WHEN role = 'ADMIN' THEN 0 ELSE 1 END, created_at ASC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if actor_id is None:
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO task_tags (id, name, normalized_name, created_by)
            SELECT gen_random_uuid(), source.name, lower(source.name), :actor_id
            FROM (
                SELECT DISTINCT btrim(tag_value) AS name
                FROM (
                    SELECT unnest(tags) AS tag_value FROM tasks
                    UNION ALL
                    SELECT unnest(applies_to_tags) AS tag_value FROM custom_rules
                ) AS raw_values
                WHERE btrim(tag_value) <> ''
            ) AS source
            ON CONFLICT (normalized_name) DO NOTHING
            """
        ),
        {"actor_id": actor_id},
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_tags_updated_at ON task_tags")
    op.drop_index("idx_task_tags_name", table_name="task_tags")
    op.drop_table("task_tags")
