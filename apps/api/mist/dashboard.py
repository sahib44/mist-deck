from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from .db import get_db, now
from .models import *
from .auth import current_user, allowed
from .services import serialize
from .tickets import ticket_scope
from .campaigns import outbox_scope

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    metrics, groups = [], {}

    def metric(label, stmt, link):
        metrics.append(
            {
                "label": label,
                "value": db.scalar(select(func.count()).select_from(stmt.subquery())),
                "link": link,
            }
        )

    if allowed(user, "judges") or allowed(user, "imports"):
        active = select(Judge).where(Judge.merged_into_id.is_(None))
        metric("Judge contacts", active, "/judges")
        groups["Contacts by status"] = [
            {"label": status, "value": count, "link": f"/judges?status={status}"}
            for status, count in db.execute(
                select(Judge.status, func.count())
                .where(Judge.merged_into_id.is_(None))
                .group_by(Judge.status)
            )
        ]
        groups["Judges by category"] = [
            {"label": name, "value": count, "link": f"/judges?category={name}"}
            for name, count in db.execute(
                select(Category.name, func.count())
                .join(JudgeCategory)
                .join(Judge)
                .where(Judge.merged_into_id.is_(None))
                .group_by(Category.name)
            )
        ]
    if allowed(user, "imports"):
        metric(
            "Duplicate reviews",
            select(Duplicate).where(
                Duplicate.resolution == "pending", Duplicate.confidence_score >= 0.7
            ),
            "/duplicates",
        )
    if allowed(user, "campaigns"):
        metric(
            "Draft campaigns",
            select(Campaign).where(Campaign.status == "draft"),
            "/campaigns?status=draft",
        )
        metric(
            "Pending approval",
            select(Campaign).where(Campaign.status == "pending_approval"),
            "/campaigns?status=pending_approval",
        )
    if allowed(user, "outbox"):
        for status in ["sent", "queued", "failed"]:
            metric(
                f"Messages {status}",
                outbox_scope(user).where(Outbound.status == status),
                f"/outbox?status={status}",
            )
    if allowed(user, "tickets") or "private_tickets" in user.permissions:
        scoped = ticket_scope(user)
        opened = scoped.where(Ticket.status.not_in(["resolved", "closed"]))
        metric("Open tickets", opened, "/tickets?view=open")
        metric(
            "Unassigned tickets",
            opened.where(Ticket.assigned_user_id.is_(None)),
            "/tickets?view=unassigned",
        )
        metric(
            "Overdue tickets",
            opened.where(Ticket.last_message_at < now() - timedelta(days=3)),
            "/tickets?view=overdue",
        )
        ids = scoped.with_only_columns(Ticket.id)
        groups["Tickets by status"] = [
            {"label": status, "value": count, "link": f"/tickets?status={status}"}
            for status, count in db.execute(
                select(Ticket.status, func.count())
                .where(Ticket.id.in_(ids))
                .group_by(Ticket.status)
            )
        ]
        groups["Tickets by committee"] = [
            {"label": name, "value": count, "link": f"/tickets?committee_id={id}"}
            for id, name, count in db.execute(
                select(Committee.id, Committee.name, func.count())
                .join(Ticket)
                .where(Ticket.id.in_(ids))
                .group_by(Committee.id, Committee.name)
            )
        ]
    recent = []
    if allowed(user, "audit"):
        recent = [
            serialize(a)
            for a in db.scalars(
                select(Audit).order_by(Audit.created_at.desc()).limit(8)
            )
        ]
        if (
            user.role == "technology_administrator"
            and "private_tickets" not in user.permissions
        ):
            for a in recent:
                if a["entity_type"] in {
                    "tickets",
                    "ticket_messages",
                    "ticket_internal_notes",
                }:
                    a["summary"], a["before_data"], a["after_data"] = (
                        "Ticket action (content restricted)",
                        None,
                        None,
                    )
    latest = (
        db.scalar(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(1))
        if allowed(user, "imports")
        else None
    )
    return {
        "metrics": metrics,
        "groups": groups,
        "recent_activity": recent,
        "latest_import": serialize(latest) if latest else None,
        "overdue_definition": "Open tickets with no public message for more than 3 days",
    }
