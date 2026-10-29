"""Competition roles, direct recipients, shared inbox, and safe directory clearing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c527aee10829"
down_revision = "91a4cb730e62"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)


def record():
    return [sa.Column("id", UUID, primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.add_column("campaign_recipients", sa.Column("recipient_name", sa.String(400), nullable=False, server_default=""))
    op.execute("UPDATE campaign_recipients r SET recipient_name=j.display_name FROM judge_contacts j WHERE r.judge_id=j.id")
    op.drop_constraint("campaign_recipients_judge_id_fkey", "campaign_recipients", type_="foreignkey")
    op.alter_column("campaign_recipients", "judge_id", nullable=True)
    op.create_foreign_key("campaign_recipients_judge_id_fkey", "campaign_recipients", "judge_contacts", ["judge_id"], ["id"], ondelete="SET NULL")
    op.create_table("inbound_messages", *record(),
        sa.Column("judge_id", UUID, sa.ForeignKey("judge_contacts.id", ondelete="SET NULL")),
        sa.Column("campaign_recipient_id", UUID, sa.ForeignKey("campaign_recipients.id")),
        sa.Column("competition_id", UUID, sa.ForeignKey("pilot_competitions.id")),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id")),
        sa.Column("sender_name", sa.String(400), nullable=False), sa.Column("sender_email", sa.String(254), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("request_id", UUID, nullable=False, unique=True), sa.Column("read_at", sa.DateTime(timezone=True)))
    op.create_table("notifications", *record(),
        sa.Column("kind", sa.String(40), nullable=False), sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False), sa.Column("href", sa.Text(), nullable=False),
        sa.Column("judge_id", UUID, sa.ForeignKey("judge_contacts.id", ondelete="SET NULL")),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id")),
        sa.Column("outbound_id", UUID, sa.ForeignKey("outbound_messages.id"), unique=True),
        sa.Column("read_at", sa.DateTime(timezone=True)))
    op.create_table("directory_backups", *record(),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("judge_count", sa.Integer(), nullable=False), sa.Column("cleared_at", sa.DateTime(timezone=True)))
    for table, columns in {"inbound_messages": ["created_at", "judge_id", "campaign_recipient_id", "competition_id", "ticket_id"], "notifications": ["created_at", "kind", "judge_id", "ticket_id"], "directory_backups": ["created_at"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.drop_table("saved_judge_lists")


def downgrade():
    op.create_table("saved_judge_lists", *record(), sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("filter_definition", postgresql.JSONB(), nullable=False), sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False))
    op.create_index("ix_saved_judge_lists_created_at", "saved_judge_lists", ["created_at"])
    for table in ["directory_backups", "notifications", "inbound_messages"]:
        op.drop_table(table)
    # A downgrade cannot safely force direct recipients into the old judge-only schema.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM campaign_recipients WHERE judge_id IS NULL")):
        raise RuntimeError("Archive direct-recipient campaign history before downgrading.")
    op.drop_constraint("campaign_recipients_judge_id_fkey", "campaign_recipients", type_="foreignkey")
    op.alter_column("campaign_recipients", "judge_id", nullable=False)
    op.create_foreign_key("campaign_recipients_judge_id_fkey", "campaign_recipients", "judge_contacts", ["judge_id"], ["id"])
    op.drop_column("campaign_recipients", "recipient_name")
