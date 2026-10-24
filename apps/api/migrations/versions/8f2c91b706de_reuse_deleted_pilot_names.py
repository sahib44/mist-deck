"""Allow deleted pilot names to be reused while keeping active names unique."""

from alembic import op
import sqlalchemy as sa

revision = "8f2c91b706de"
down_revision = "2ec531a5470a"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("pilot_competitions_name_event_year_key", "pilot_competitions", type_="unique")
    op.create_index(
        "uq_active_competition_name_year",
        "pilot_competitions",
        [sa.text("lower(name)"), "event_year"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade():
    op.drop_index("uq_active_competition_name_year", table_name="pilot_competitions")
    op.create_unique_constraint(
        "pilot_competitions_name_event_year_key",
        "pilot_competitions",
        ["name", "event_year"],
    )
