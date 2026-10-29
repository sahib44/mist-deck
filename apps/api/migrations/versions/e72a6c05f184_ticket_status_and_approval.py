"""Atomic ticket status actions, chair review, and inactivity deadlines."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e72a6c05f184"
down_revision = "d61f3b9720ac"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)


def record():
    return [sa.Column("id", UUID, primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.add_column("tickets", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tickets", sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""))
    op.add_column("tickets", sa.Column("auto_close_at", sa.DateTime(timezone=True)))
    op.create_index("ix_tickets_auto_close_at", "tickets", ["auto_close_at"])
    op.add_column("ticket_internal_notes", sa.Column("kind", sa.String(30), nullable=False, server_default="internal"))
    op.add_column("ticket_internal_notes", sa.Column("request_id", UUID))
    op.create_unique_constraint("uq_ticket_notes_request_id", "ticket_internal_notes", ["request_id"])
    op.create_table("ticket_drafts", *record(),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_status", sa.String(40), nullable=False), sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_id", UUID, nullable=False, unique=True),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id")), sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.create_table("ticket_actions", *record(),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", UUID, nullable=False, unique=True), sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False))
    for table, columns in {"ticket_drafts": ["created_at", "ticket_id", "created_by", "status"], "ticket_actions": ["created_at", "ticket_id"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.add_column("notifications", sa.Column("recipient_user_id", UUID, sa.ForeignKey("users.id")))
    op.add_column("notifications", sa.Column("draft_id", UUID, sa.ForeignKey("ticket_drafts.id")))
    for column in ("recipient_user_id", "draft_id"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])
    op.execute("UPDATE notifications n SET read_at=NULL FROM tickets t WHERE n.ticket_id=t.id AND n.kind='ticket' AND t.status='new'")
    op.execute("UPDATE tickets SET auto_close_at=COALESCE(resolved_at,last_message_at)+interval '7 days' WHERE status='resolved'")
    op.execute("""UPDATE tickets t SET auto_close_at=(SELECT max(o.completed_at)+interval '7 days' FROM outbound_messages o JOIN ticket_messages m ON m.outbound_message_id=o.id WHERE m.ticket_id=t.id AND m.message_type='staff_reply' AND o.status='sent') WHERE t.status='waiting_on_requester'""")


def downgrade():
    for column in ("draft_id", "recipient_user_id"):
        op.drop_column("notifications", column)
    op.drop_table("ticket_actions")
    op.drop_table("ticket_drafts")
    op.drop_column("ticket_internal_notes", "request_id")
    op.drop_column("ticket_internal_notes", "kind")
    for column in ("auto_close_at", "resolution_note", "version"):
        op.drop_column("tickets", column)
    op.execute("UPDATE tickets SET status='waiting_on_organizer' WHERE status='in_progress'")
