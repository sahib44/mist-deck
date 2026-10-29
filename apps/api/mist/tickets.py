from uuid import UUID, uuid4, uuid5
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, or_, update
from .db import get_db, now
from .models import *
from .schemas import (
    TicketIn,
    ForwardIn,
    TicketStatus,
    TicketDraftIn,
    Content,
    ObjectView,
    Page,
    Input,
)
from .auth import current_user, allowed, fail
from .services import *

router = APIRouter(prefix="/api")
from .ticket_flow import TRANSITIONS, STATUSES, apply_status_action, text_value, changed, mark_ticket_notifications, supersede_drafts, consume_approval


def ticket_scope(user):
    # Every ticket belongs to the shared competitions mailbox.
    return select(Ticket).where(allowed(user, "tickets") or "private_tickets" in user.permissions)


def ticket_user(user=Depends(current_user)):
    if not (allowed(user, "tickets") or "private_tickets" in user.permissions):
        fail("forbidden", "Your account has no private ticket access.", 403)
    return user


def ticket_get(db, user, id, lock=False):
    stmt = ticket_scope(user).where(Ticket.id == id)
    if lock:
        stmt = stmt.with_for_update()
    ticket = db.scalar(stmt)
    if not ticket:
        fail("not_found", "Ticket not found or access is restricted.", 404)
    return ticket


@router.get("/tickets", response_model=Page)
def tickets(
    request: Request,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(ticket_user),
    db=Depends(get_db),
):
    params = request.query_params
    stmt = ticket_scope(user)
    if q := params.get("q"):
        stmt = stmt.where(
            or_(
                Ticket.subject.ilike(f"%{q}%"),
                Ticket.public_number.ilike(f"%{q}%"),
                Ticket.requester_name.ilike(f"%{q}%"),
                Ticket.requester_email.ilike(f"%{q}%"),
            )
        )
    if value := params.get("status"):
        if value not in TRANSITIONS:
            fail("invalid_status", "Choose a valid ticket status.")
        stmt = stmt.where(Ticket.status == value)
    if params.get("view") == "waiting":
        stmt = stmt.where(Ticket.status.in_(["new", "in_progress", "waiting_on_organizer"]))
    elif params.get("view") == "open":
        stmt = stmt.where(Ticket.status.not_in(["resolved", "closed"]))
    elif params.get("view") == "overdue":
        from datetime import timedelta
        stmt = stmt.where(Ticket.status.not_in(["resolved", "closed"]), Ticket.last_message_at < now() - timedelta(days=3))
    sort = params.get("sort", "newest")
    ordering = {
        "newest": Ticket.created_at.desc(),
        "oldest": Ticket.created_at,
        "activity": Ticket.last_message_at.desc(),
    }
    return page(
        db,
        stmt.order_by(ordering.get(sort, Ticket.created_at.desc()), Ticket.id),
        page_no,
        page_size,
    )


@router.post("/tickets", response_model=ObjectView)
def create(data: TicketIn, user=Depends(ticket_user), db=Depends(get_db)):
    address = contact_email(data.requester_email)
    number = db.scalar(select(ticket_sequence.next_value()))
    ticket = Ticket(
        public_number=f"MD-{number:06d}",
        requester_name=clean(data.requester_name),
        requester_email=address,
        subject=clean(data.subject),
        source="simulated_email",
        created_by=user.id,
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            message_type="requester_message",
            sender_name=ticket.requester_name,
            sender_email=address,
            body=clean(data.body),
            created_by=user.id,
        )
    )
    audit(db, user, "ticket.created", ticket, "Incoming competitions ticket created")
    from .inbox import notify
    notify(db, "ticket", f"New ticket: {ticket.requester_name}", ticket.subject, f"/tickets/{ticket.id}", ticket_id=ticket.id)
    db.commit()
    return serialize(ticket)


class TicketBulk(Input):
    ids: list[UUID]
    status: TicketStatus
    confirmed: bool


@router.post("/tickets/bulk")
def bulk(data: TicketBulk, user=Depends(ticket_user), db=Depends(get_db)):
    if not data.confirmed or not 1 <= len(data.ids) <= 1000:
        fail("confirmation_required", "Confirm between 1 and 1000 tickets.")
    if data.status.status not in {"in_progress", "closed"}:
        fail("individual_status_required", "Open each ticket to provide its required reply or note.")
    for id in sorted(set(data.ids)):
        ticket = ticket_get(db, user, id, True)
        action = data.status.model_copy(update={"request_id": uuid5(data.status.request_id, str(id))})
        apply_status_action(db, ticket, action, user)
    db.commit()
    return {"updated": len(set(data.ids))}


@router.get("/tickets/{id}", response_model=ObjectView)
def detail(id: UUID, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id)
    return {
        **serialize(ticket),
        "allowed_transitions": sorted(TRANSITIONS[ticket.status]),
    }


@router.get("/tickets/{id}/drafts", response_model=Page)
def ticket_drafts(id: UUID, user=Depends(ticket_user), db=Depends(get_db)):
    ticket_get(db, user, id)
    stmt = select(TicketDraft).where(TicketDraft.ticket_id == id)
    if not allowed(user, "ticket_approve"):
        stmt = stmt.where(TicketDraft.created_by == user.id)
    def view(draft):
        author = db.get(User, draft.created_by)
        return {**serialize(draft), "author_name": author.full_name if author else "Organizer"}
    return page(db, stmt.order_by(TicketDraft.created_at.desc(), TicketDraft.id.desc()), 1, 100, view)


@router.post("/tickets/{id}/drafts", response_model=ObjectView)
def request_chair_review(id: UUID, data: TicketDraftIn, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    body, resolution = text_value(data.body), text_value(data.resolution_note)
    if data.target_status and data.target_status not in STATUSES:
        fail("invalid_status", "Choose a valid ticket status.")
    if not body and not (data.target_status == "resolved" and resolution):
        fail("draft_required", "Write a draft before requesting chair approval.")
    existing = db.scalar(select(TicketDraft).where(TicketDraft.request_id == data.request_id))
    if existing:
        if existing.ticket_id != id or existing.created_by != user.id or (existing.kind, existing.body, existing.target_status, existing.resolution_note) != (data.kind, body, data.target_status, resolution):
            fail("request_reused", "This request ID was already used.", 409)
        return serialize(existing)
    if data.expected_version != ticket.version:
        fail("ticket_changed", "The ticket changed. Review the latest messages before requesting approval.", 409)
    chairs = db.scalars(select(User).where(User.role == "competitions_chair", User.is_active.is_(True))).all()
    if not chairs:
        fail("chair_unavailable", "No active competitions chair is available for approval.")
    supersede_drafts(db, ticket, author_id=user.id, kind=data.kind)
    draft = TicketDraft(ticket_id=id, created_by=user.id, kind=data.kind, body=body, target_status=data.target_status, resolution_note=resolution, base_version=ticket.version, request_id=data.request_id)
    db.add(draft)
    db.flush()
    from .inbox import notify
    for chair in chairs:
        notify(db, "ticket_approval_requested", f"Chair approval requested: {ticket.public_number}", f"{user.full_name} submitted a {'reply' if data.kind == 'messages' else 'private note'} for review.", f"/tickets/{id}?draft={draft.id}", ticket_id=id, draft_id=draft.id, recipient_user_id=chair.id)
    audit(db, user, "ticket.approval_requested", ticket, "Draft submitted for chair approval", after={"draft_id": str(draft.id)})
    db.commit()
    return serialize(draft)


@router.post("/tickets/{id}/drafts/{draft_id}/approve", response_model=ObjectView)
def approve_ticket_draft(id: UUID, draft_id: UUID, user=Depends(ticket_user), db=Depends(get_db)):
    if not allowed(user, "ticket_approve"):
        fail("forbidden", "Only the competitions chair or a director can approve ticket drafts.", 403)
    ticket = ticket_get(db, user, id, True)
    draft = get(db, TicketDraft, draft_id, True)
    if draft.ticket_id != id:
        fail("not_found", "Draft not found in this ticket.", 404)
    if draft.status == "approved":
        return serialize(draft)
    if draft.status != "pending_approval" or draft.base_version != ticket.version:
        fail("stale_draft", "This draft or ticket changed. Ask the head to submit a fresh draft.", 409)
    draft.status, draft.approved_by, draft.approved_at = "approved", user.id, now()
    db.execute(update(Notification).where(Notification.draft_id == draft.id).values(read_at=now()))
    from .inbox import notify
    notify(db, "ticket_draft_approved", f"Draft approved: {ticket.public_number}", "The chair approved your draft. Open the ticket to review it and make the final send or save.", f"/tickets/{id}?draft={draft.id}", ticket_id=id, draft_id=draft.id, recipient_user_id=draft.created_by)
    audit(db, user, "ticket.draft_approved", ticket, "Chair approved a ticket draft", after={"draft_id": str(draft.id)})
    db.commit()
    return serialize(draft)


@router.get("/tickets/{id}/{kind}", response_model=Page)
def thread(
    id: UUID,
    kind: str,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(ticket_user),
    db=Depends(get_db),
):
    ticket_get(db, user, id)
    cls = {"messages": TicketMessage, "notes": TicketNote, "activity": Audit}.get(kind)
    if not cls:
        fail("not_found", "Unknown ticket view.", 404)
    stmt = (
        select(cls).where(Audit.entity_id == str(id))
        if cls == Audit
        else select(cls).where(cls.ticket_id == id)
    )
    order = (cls.created_at.desc(), cls.id.desc()) if kind == "notes" else (cls.created_at, cls.id)
    return page(db, stmt.order_by(*order), page_no, page_size)


@router.post("/tickets/{id}/status", response_model=ObjectView)
def status(id: UUID, data: TicketStatus, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    result = apply_status_action(db, ticket, data, user)
    db.commit()
    return result


@router.post("/tickets/{id}/messages", response_model=ObjectView)
def reply(id: UUID, data: Content, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    result = apply_status_action(db, ticket, TicketStatus(status="waiting_on_requester", reply_body=data.body, request_id=data.request_id, approval_id=data.approval_id), user)
    public = get(db, TicketMessage, UUID(result["reply_message_id"]))
    db.commit()
    return serialize(public)


@router.post("/tickets/{id}/notes", response_model=ObjectView)
def note(id: UUID, data: Content, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    body = text_value(data.body)
    if not body:
        fail("note_required", "Enter an internal note.")
    existing = db.scalar(select(TicketNote).where(TicketNote.request_id == data.request_id))
    if existing:
        if existing.ticket_id != id or existing.created_by != user.id or existing.body != body:
            fail("request_reused", "This note ID was already used.", 409)
        return serialize(existing)
    if data.approval_id:
        consume_approval(db, ticket, user, data.approval_id, "notes", body, "", "")
    note = TicketNote(ticket_id=id, body=body, created_by=user.id, request_id=data.request_id)
    db.add(note)
    changed(db, ticket)
    audit(db, user, "ticket.internal_note", ticket, "Private internal note added")
    db.commit()
    return serialize(note)


@router.post("/tickets/{id}/messages/{message_id}/forward", response_model=ObjectView)
def forward_ticket_message(id: UUID, message_id: UUID, data: ForwardIn, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id)
    original = get(db, TicketMessage, message_id)
    if original.ticket_id != id:
        fail("not_found", "Message not found in this ticket.", 404)
    address = contact_email(data.recipient_email)
    if address == ticket.requester_email and not allowed(user, "ticket_approve"):
        fail("chair_approval_required", "Use the approved public reply flow to email this requester.", 403)
    note = clean(data.note).strip()
    body = (note + "\n\n") if note else ""
    body += f"---------- Forwarded message ----------\nFrom: {original.sender_name} <{original.sender_email}>\nSubject: {ticket.subject}\n\n{original.body}"
    message = Outbound(recipient_email=address, recipient_name=address, subject=f"Fwd: {ticket.subject}", body_text=body, related_ticket_id=id, idempotency_key=f"ticket-forward:{uuid4()}")
    db.add(message)
    audit(db, user, "ticket.message_forwarded", ticket, "Queued a sandbox email forward", after={"recipient_email": address, "message_id": str(message_id)})
    db.commit()
    return serialize(message)
