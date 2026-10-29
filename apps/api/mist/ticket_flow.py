"""Atomic ticket changes and immutable, chair-reviewed reply snapshots."""
import hashlib
import json
from datetime import timedelta
from sqlalchemy import select, update
from .auth import allowed, fail
from .db import now
from .models import Ticket, TicketMessage, TicketNote, TicketDraft, TicketAction, Notification, Outbound
from .services import audit, clean, contact_email, serialize

STATUSES = {"new", "in_progress", "waiting_on_organizer", "waiting_on_requester", "resolved", "closed"}
TRANSITIONS = {
    "new": {"in_progress", "waiting_on_organizer", "waiting_on_requester", "resolved"},
    "in_progress": {"waiting_on_organizer", "waiting_on_requester", "resolved"},
    "waiting_on_organizer": {"in_progress", "waiting_on_requester", "resolved"},
    "waiting_on_requester": {"in_progress", "waiting_on_organizer", "resolved"},
    "resolved": {"closed", "in_progress", "waiting_on_organizer", "waiting_on_requester"},
    "closed": {"in_progress", "waiting_on_organizer"},
}


def text_value(value):
    return clean(value).strip()


def supersede_drafts(db, ticket, author_id=None, kind=None):
    stmt = select(TicketDraft).where(TicketDraft.ticket_id == ticket.id, TicketDraft.status.in_(["pending_approval", "approved"]))
    if author_id:
        stmt = stmt.where(TicketDraft.created_by == author_id)
    if kind:
        stmt = stmt.where(TicketDraft.kind == kind)
    ids = []
    for draft in db.scalars(stmt):
        draft.status = "superseded"
        ids.append(draft.id)
    if ids:
        db.execute(update(Notification).where(Notification.draft_id.in_(ids)).values(read_at=now()))


def changed(db, ticket):
    ticket.version += 1
    supersede_drafts(db, ticket)


def mark_ticket_notifications(db, ticket):
    if ticket.status != "new":
        db.execute(update(Notification).where(Notification.ticket_id == ticket.id, Notification.kind == "ticket", Notification.read_at.is_(None)).values(read_at=now()))


def consume_approval(db, ticket, user, approval_id, kind, body, target_status, resolution_note):
    if allowed(user, "ticket_approve") and not approval_id:
        return
    if not approval_id:
        fail("chair_approval_required", "Request chair approval for this reply before sending.", 403)
    draft = db.scalar(select(TicketDraft).where(TicketDraft.id == approval_id).with_for_update())
    if not draft or draft.ticket_id != ticket.id or draft.created_by != user.id or draft.status != "approved":
        fail("chair_approval_required", "This draft has not been approved for your account.", 403)
    if (draft.base_version != ticket.version or draft.kind != kind or draft.body != body or draft.target_status != target_status or draft.resolution_note != resolution_note):
        fail("approval_changed", "The reply or ticket changed. Request chair approval again.", 409)
    draft.status = "used"
    db.execute(update(Notification).where(Notification.draft_id == draft.id).values(read_at=now()))


def queue_reply(db, ticket, user, body, request_id):
    message = Outbound(recipient_email=contact_email(ticket.requester_email), recipient_name=ticket.requester_name, subject=f"Re: {ticket.public_number} — {ticket.subject}", body_text=body, related_ticket_id=ticket.id, idempotency_key=f"ticket:{ticket.id}:{request_id}")
    db.add(message)
    db.flush()
    public = TicketMessage(ticket_id=ticket.id, message_type="staff_reply", sender_name=user.full_name, sender_email=user.email, body=body, created_by=user.id, outbound_message_id=message.id)
    db.add(public)
    ticket.last_message_at = now()
    audit(db, user, "ticket.replied", ticket, "Public reply queued in sandbox")
    return public


def apply_status_action(db, ticket, data, user):
    body = text_value(data.reply_body)
    internal = text_value(data.internal_note)
    resolution = text_value(data.resolution_note)
    payload = {"status": data.status, "reply_body": body, "internal_note": internal, "resolution_note": resolution}
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(TicketAction).where(TicketAction.request_id == data.request_id))
    if existing:
        if existing.ticket_id != ticket.id or existing.created_by != user.id or existing.signature != signature:
            fail("request_reused", "This action ID was already used for a different change.", 409)
        return existing.result
    if data.expected_version is not None and data.expected_version != ticket.version:
        fail("ticket_changed", "This ticket changed. Review the latest messages before saving.", 409)
    if data.status != ticket.status and data.status not in TRANSITIONS[ticket.status]:
        fail("invalid_transition", f"Cannot move {ticket.status} to {data.status}.")
    if data.status == "waiting_on_requester" and not body:
        fail("reply_required", "A public reply is required for Waiting on requester.")
    if data.status == "waiting_on_organizer" and not internal:
        fail("internal_note_required", "Add an internal note explaining the team's next step.")
    if data.status == "resolved" and not resolution:
        fail("resolution_required", "A resolution note is required to resolve this ticket.")
    if body:
        consume_approval(db, ticket, user, data.approval_id, "messages", body, data.status, resolution)
    elif data.approval_id:
        consume_approval(db, ticket, user, data.approval_id, "notes" if internal else "messages", internal, data.status, resolution)
    before = serialize(ticket)
    public = queue_reply(db, ticket, user, body, data.request_id) if body else None
    for kind, note_body in (("internal", internal), ("resolution", resolution)):
        if note_body:
            db.add(TicketNote(ticket_id=ticket.id, body=note_body, kind=kind, created_by=user.id))
            audit(db, user, "ticket.internal_note", ticket, "Resolution note added" if kind == "resolution" else "Private internal note added")
    ticket.status = data.status
    ticket.resolved_at = now() if data.status == "resolved" else ticket.resolved_at if data.status == "closed" else None
    ticket.closed_at = now() if data.status == "closed" else None
    ticket.auto_close_at = now() + timedelta(days=7) if data.status == "resolved" else None
    if data.status == "resolved":
        ticket.resolution_note = resolution
    ticket.updated_by = user.id
    changed(db, ticket)
    mark_ticket_notifications(db, ticket)
    audit(db, user, "ticket.status_changed", ticket, f"Ticket status: {data.status}", before, serialize(ticket))
    db.flush()
    result = {**serialize(ticket), "reply_message_id": str(public.id) if public else None}
    db.add(TicketAction(ticket_id=ticket.id, created_by=user.id, request_id=data.request_id, signature=signature, result=result))
    return result


def close_idle_tickets(db):
    items = db.scalars(select(Ticket).where(Ticket.status.in_(["waiting_on_requester", "resolved"]), Ticket.auto_close_at <= now()).order_by(Ticket.id).with_for_update(skip_locked=True).limit(100)).all()
    for ticket in items:
        before = serialize(ticket)
        ticket.status, ticket.closed_at, ticket.auto_close_at = "closed", now(), None
        changed(db, ticket)
        mark_ticket_notifications(db, ticket)
        audit(db, None, "ticket.auto_closed", ticket, "Ticket auto-closed after 7 days without a requester reply", before, serialize(ticket))
    db.commit()
    return len(items)
