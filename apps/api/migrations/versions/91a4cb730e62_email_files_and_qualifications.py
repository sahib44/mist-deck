"""Store per-competition qualification text and sandbox email attachments/forwards."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "91a4cb730e62"
down_revision = "8f2c91b706de"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pilot_nominations", sa.Column("qualification_text", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "campaign_attachments",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_attachments_campaign_id", "campaign_attachments", ["campaign_id"])
    op.create_index("ix_campaign_attachments_created_at", "campaign_attachments", ["created_at"])
    op.add_column("outbound_messages", sa.Column("forwarded_from_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_outbound_forwarded_from", "outbound_messages", "outbound_messages", ["forwarded_from_id"], ["id"])
    op.create_index("ix_outbound_messages_forwarded_from_id", "outbound_messages", ["forwarded_from_id"])


def downgrade():
    op.drop_index("ix_outbound_messages_forwarded_from_id", table_name="outbound_messages")
    op.drop_constraint("fk_outbound_forwarded_from", "outbound_messages", type_="foreignkey")
    op.drop_column("outbound_messages", "forwarded_from_id")
    op.drop_table("campaign_attachments")
    op.drop_column("pilot_nominations", "qualification_text")
