"""Pilot competitions, private documents, and per-competition nominations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9b42a07f6c31"
down_revision = "3cc631c46f1c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pilot_competitions",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("event_year", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "event_year"),
    )
    op.create_index("ix_pilot_competitions_event_year", "pilot_competitions", ["event_year"])
    op.create_index("ix_pilot_competitions_created_at", "pilot_competitions", ["created_at"])
    op.create_table(
        "pilot_nominations",
        sa.Column("pilot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("judge_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True)),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilot_competitions.id"]),
        sa.ForeignKeyConstraint(["judge_id"], ["judge_contacts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pilot_id", "judge_id"),
    )
    for field in ("pilot_id", "judge_id", "status", "created_at"):
        op.create_index(f"ix_pilot_nominations_{field}", "pilot_nominations", [field])
    op.create_table(
        "pilot_documents",
        sa.Column("pilot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilot_competitions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pilot_id", "kind"),
    )
    op.create_index("ix_pilot_documents_pilot_id", "pilot_documents", ["pilot_id"])
    op.create_index("ix_pilot_documents_created_at", "pilot_documents", ["created_at"])
    op.add_column(
        "campaigns",
        sa.Column("pilot_competition_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_campaigns_pilot_competition_id", "campaigns", "pilot_competitions",
        ["pilot_competition_id"], ["id"],
    )
    op.create_index("ix_campaigns_pilot_competition_id", "campaigns", ["pilot_competition_id"])


def downgrade():
    op.drop_index("ix_campaigns_pilot_competition_id", table_name="campaigns")
    op.drop_constraint("fk_campaigns_pilot_competition_id", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "pilot_competition_id")
    op.drop_table("pilot_documents")
    op.drop_table("pilot_nominations")
    op.drop_table("pilot_competitions")
