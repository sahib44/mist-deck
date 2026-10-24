"""Add category and permanence to competition workspaces."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2ec531a5470a"
down_revision = "9b42a07f6c31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pilot_competitions", sa.Column("category_slug", sa.String(80), nullable=False, server_default="group-projects"))
    op.add_column("pilot_competitions", sa.Column("is_pilot", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("pilot_competitions", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("pilot_competitions", sa.Column("deleted_by", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_pilot_competitions_deleted_by", "pilot_competitions", "users", ["deleted_by"], ["id"])
    op.create_index("ix_pilot_competitions_category_slug", "pilot_competitions", ["category_slug"])
    op.create_index("ix_pilot_competitions_is_pilot", "pilot_competitions", ["is_pilot"])


def downgrade():
    op.drop_index("ix_pilot_competitions_is_pilot", table_name="pilot_competitions")
    op.drop_index("ix_pilot_competitions_category_slug", table_name="pilot_competitions")
    op.drop_constraint("fk_pilot_competitions_deleted_by", "pilot_competitions", type_="foreignkey")
    for column in ("deleted_by", "deleted_at", "is_pilot", "category_slug"):
        op.drop_column("pilot_competitions", column)
