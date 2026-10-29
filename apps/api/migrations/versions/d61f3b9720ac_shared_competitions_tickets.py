"""Simplify competitions tickets to shared email conversations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d61f3b9720ac"
down_revision = "c527aee10829"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE tickets SET status='waiting_on_organizer' WHERE status='assigned'")
    op.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE role='support_staff')")
    op.execute("UPDATE users SET is_active=false WHERE role='support_staff'")
    for column in ("assigned_user_id", "committee_id", "category_id", "priority"):
        op.drop_column("tickets", column)


def downgrade():
    op.add_column("tickets", sa.Column("priority", sa.String(30), nullable=False, server_default="normal"))
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    for column, target, indexed in [("committee_id", "committees", True), ("category_id", "competition_categories", False), ("assigned_user_id", "users", True)]:
        op.add_column("tickets", sa.Column(column, postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{target}.id")))
        if indexed:
            op.create_index(f"ix_tickets_{column}", "tickets", [column])
