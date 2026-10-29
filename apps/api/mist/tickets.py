from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, or_, case
from .db import get_db, now
from .models import *
from .schemas import (
    TicketIn,
    Assignment,
    TicketStatus,
    Content,
    ObjectView,
    Page,
    Input,
)
from .auth import current_user, allowed, fail, COMPETITIONS_ROLES
from .services import *

router = APIRouter(prefix="/api")
TRANSITIONS = {
    "new": {"assigned", "waiting_on_organizer", "resolved"},
    "assigned": {"waiting_on_organizer", "waiting_on_requester", "resolved"},
    "waiting_on_organizer": {"assigned", "waiting_on_requester", "resolved"},
    "waiting_on_requester": {"assigned", "waiting_on_organizer", "resolved"},
    "resolved": {"closed", "assigned"},
    "closed": {"assigned"},
}


def ticket_scope(user):
    stmt = select(Ticket)
    if user.role == "director" or "private_tickets" in user.permissions:
        return stmt
    if user.role == "support_staff":
        return stmt.where(Ticket.assigned_user_id == user.id)
    if user.role in COMPETITIONS_ROLES:
        return stmt.where(
            or_(
                Ticket.category_id.is_not(None),
                Ticket.committee_id.in_(
                    select(Committee.id).where(Committee.name == "Competitions")
                ),
                Ticket.assigned_user_id == user.id,
                Ticket.created_by == user.id,
            )
        )
    return stmt.where(False)


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


def set_assignment(db, ticket, data, user):
    if user.role == "support_staff":
        fail("forbidden", "Support staff cannot reassign tickets.", 403)
    if data.assigned_user_id:
        assignee = get(db, User, data.assigned_user_id)
        if not assignee.is_active or not (
            allowed(assignee, "tickets") or "private_tickets" in assignee.permissions
        ):
            fail("invalid_assignee", "Select an active organizer with ticket access.")
    if data.committee_id:
        get(db, Committee, data.committee_id)
    before = serialize(ticket)
    if "category_id" in data.model_fields_set:
        if data.category_id:
            get(db, Category, data.category_id)
        ticket.category_id = data.category_id
    ticket.assigned_user_id, ticket.committee_id = (
        data.assigned_user_id,
        data.committee_id,
    )
    if ticket.status == "new" and (data.assigned_user_id or data.committee_id):
        ticket.status = "assigned"
    ticket.updated_by = user.id
    audit(
        db,
        user,
        "ticket.assigned",
        ticket,
        "Ticket assignment changed",
        before,
        serialize(ticket),
    )
    if before["status"] != ticket.status:
        audit(
            db, user, "ticket.status_changed", ticket, f"Ticket status: {ticket.status}"
        )


def set_status(db, ticket, data, user):
    if data.status != ticket.status and data.status not in TRANSITIONS[ticket.status]:
        fail("invalid_transition", f"Cannot move {ticket.status} to {data.status}.")
    before = serialize(ticket)
    ticket.status = data.status
    if data.priority:
        ticket.priority = data.priority
    ticket.resolved_at = (
        now()
        if data.status == "resolved"
        else ticket.resolved_at if data.status == "closed" else None
    )
    ticket.closed_at = now() if data.status == "closed" else None
    ticket.updated_by = user.id
    audit(
        db,
        user,
        "ticket.status_changed",
        ticket,
        f"Ticket status: {data.status}",
        before,
        serialize(ticket),
    )


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
    for key in [
        "status",
        "priority",
        "committee_id",
        "category_id",
        "assigned_user_id",
    ]:
        if value := params.get(key):
            if key.endswith("_id"):
                try:
                    value = UUID(value)
                except ValueError:
                    fail("invalid_filter", "Select a valid filter value.")
            stmt = stmt.where(getattr(Ticket, key) == value)
    if params.get("view") == "mine":
        stmt = stmt.where(
            Ticket.assigned_user_id == user.id,
            Ticket.status.not_in(["resolved", "closed"]),
        )
    elif params.get("view") == "unassigned":
        stmt = stmt.where(
            Ticket.assigned_user_id.is_(None),
            Ticket.status.not_in(["resolved", "closed"]),
        )
    elif params.get("view") == "waiting":
        stmt = stmt.where(Ticket.status == "waiting_on_organizer")
    elif params.get("view") == "open":
        stmt = stmt.where(Ticket.status.not_in(["resolved", "closed"]))
    elif params.get("view") == "overdue":
        from datetime import timedelta

        stmt = stmt.where(
            Ticket.status.not_in(["resolved", "closed"]),
            Ticket.last_message_at < now() - timedelta(days=3),
        )
    sort = params.get("sort", "newest")
    ordering = {
        "newest": Ticket.created_at.desc(),
        "oldest": Ticket.created_at,
        "activity": Ticket.last_message_at.desc(),
        "priority": case(
            (Ticket.priority == "urgent", 0),
            (Ticket.priority == "high", 1),
            (Ticket.priority == "normal", 2),
            else_=3,
        ),
    }
    return page(
        db,
        stmt.order_by(ordering.get(sort, Ticket.created_at.desc()), Ticket.id),
        page_no,
        page_size,
    )


@router.post("/tickets", response_model=ObjectView)
def create(data: TicketIn, user=Depends(ticket_user), db=Depends(get_db)):
    if user.role == "support_staff":
        fail("forbidden", "An organizer must create and assign tickets.", 403)
    address = contact_email(data.requester_email)
    if data.category_id:
        get(db, Category, data.category_id)
    if data.committee_id:
        get(db, Committee, data.committee_id)
    number = db.scalar(select(ticket_sequence.next_value()))
    ticket = Ticket(
        public_number=f"MD-{number:06d}",
        requester_name=clean(data.requester_name),
        requester_email=address,
        subject=clean(data.subject),
        committee_id=data.committee_id,
        category_id=data.category_id,
        priority=data.priority,
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
    assignment: Assignment | None = None
    status: TicketStatus | None = None
    confirmed: bool


@router.post("/tickets/bulk")
def bulk(data: TicketBulk, user=Depends(ticket_user), db=Depends(get_db)):
    if not data.confirmed or not 1 <= len(data.ids) <= 1000:
        fail("confirmation_required", "Confirm between 1 and 1000 tickets.")
    for id in sorted(set(data.ids)):
        ticket = ticket_get(db, user, id, True)
        if data.assignment:
            set_assignment(db, ticket, data.assignment, user)
        if data.status:
            set_status(db, ticket, data.status, user)
    db.commit()
    return {"updated": len(set(data.ids))}


@router.get("/tickets/{id}", response_model=ObjectView)
def detail(id: UUID, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id)
    return {
        **serialize(ticket),
        "allowed_transitions": sorted(TRANSITIONS[ticket.status]),
    }


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
    return page(db, stmt.order_by(cls.created_at), page_no, page_size)


@router.post("/tickets/{id}/assign", response_model=ObjectView)
def assign(id: UUID, data: Assignment, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    set_assignment(db, ticket, data, user)
    db.commit()
    return serialize(ticket)


@router.post("/tickets/{id}/status", response_model=ObjectView)
def status(id: UUID, data: TicketStatus, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    set_status(db, ticket, data, user)
    db.commit()
    return serialize(ticket)


@router.post("/tickets/{id}/messages", response_model=ObjectView)
def reply(id: UUID, data: Content, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    if ticket.status == "closed":
        fail("ticket_closed", "Reopen the ticket before replying.")
    key = f"ticket:{id}:{data.request_id}"
    existing = db.scalar(select(Outbound).where(Outbound.idempotency_key == key))
    if existing:
        return serialize(
            db.scalar(
                select(TicketMessage).where(
                    TicketMessage.outbound_message_id == existing.id
                )
            )
        )
    message = Outbound(
        recipient_email=contact_email(ticket.requester_email),
        recipient_name=ticket.requester_name,
        subject=f"Re: {ticket.public_number} — {ticket.subject}",
        body_text=clean(data.body),
        related_ticket_id=id,
        idempotency_key=key,
    )
    db.add(message)
    db.flush()
    reply = TicketMessage(
        ticket_id=id,
        message_type="staff_reply",
        sender_name=user.full_name,
        sender_email=user.email,
        body=clean(data.body),
        created_by=user.id,
        outbound_message_id=message.id,
    )
    db.add(reply)
    ticket.last_message_at = now()
    old_status = ticket.status
    ticket.status = "waiting_on_requester"
    ticket.resolved_at, ticket.closed_at = None, None
    audit(db, user, "ticket.replied", ticket, "Public reply queued in sandbox")
    if old_status != ticket.status:
        audit(
            db,
            user,
            "ticket.status_changed",
            ticket,
            "Ticket status: waiting_on_requester",
        )
    db.commit()
    return serialize(reply)


@router.post("/tickets/{id}/notes", response_model=ObjectView)
def note(id: UUID, data: Content, user=Depends(ticket_user), db=Depends(get_db)):
    ticket = ticket_get(db, user, id, True)
    note = TicketNote(ticket_id=id, body=clean(data.body), created_by=user.id)
    db.add(note)
    audit(db, user, "ticket.internal_note", ticket, "Private internal note added")
    db.commit()
    return serialize(note)
