"""Shared team inbox. Incoming messages are simulated until a mailbox is connected."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, update, union_all, literal
from .auth import require, current_user, allowed, fail
from .db import get_db, now
from .models import Judge, Recipient, Campaign, InboundMessage, Notification, Ticket, TicketMessage, Committee, ticket_sequence
from .schemas import IncomingEmail, ConversationRead, Page
from .services import get, serialize, contact_email, clean

router = APIRouter(prefix="/api")


def notify(db, kind, title, body, href, **links):
    # A failed outbound message has one persistent notification across retries.
    if links.get("outbound_id"):
        existing = db.scalar(select(Notification).where(Notification.outbound_id == links["outbound_id"]))
        if existing:
            existing.read_at = None
            existing.body = body
            return existing
    item = Notification(kind=kind, title=title, body=body, href=href, **links)
    db.add(item)
    return item


def notification_scope(user):
    from .tickets import ticket_scope
    clauses = []
    if allowed(user, "campaigns"):
        clauses.append(Notification.kind.in_(["judge_reply", "delivery_failed"]) & Notification.ticket_id.is_(None))
    if allowed(user, "tickets") or "private_tickets" in user.permissions:
        clauses.append(Notification.ticket_id.in_(ticket_scope(user).with_only_columns(Ticket.id)))
    return select(Notification).where(or_(*clauses) if clauses else False)


@router.get("/notifications")
def notifications(user=Depends(current_user), db=Depends(get_db)):
    stmt = notification_scope(user)
    unread = db.scalar(select(func.count()).select_from(stmt.where(Notification.read_at.is_(None)).subquery()))
    return {"unread_count": unread, "items": [serialize(n) for n in db.scalars(stmt.order_by(Notification.read_at.is_not(None), Notification.created_at.desc()).limit(100))]}


@router.post("/notifications/{id}/read")
def read_notification(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    item = db.scalar(notification_scope(user).where(Notification.id == id).with_for_update())
    if not item:
        fail("not_found", "Notification not found.", 404)
    # Judge replies stay unread until their conversation is opened.
    if item.kind != "judge_reply":
        item.read_at = now()
        db.commit()
    return {"ok": True}


@router.get("/recipient-search")
def recipient_search(q: str = "", ids: str = "", user=Depends(require("campaigns")), db=Depends(get_db)):
    stmt = select(Judge).where(Judge.merged_into_id.is_(None))
    if ids:
        try:
            selected = [UUID(value) for value in ids.split(",")]
        except ValueError:
            fail("invalid_recipients", "Selected judges are invalid.")
        if len(selected) > 5000:
            fail("recipient_limit", "Too many recipients.")
        stmt = stmt.where(Judge.id.in_(selected))
    else:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Judge.display_name.ilike(term), Judge.primary_email.ilike(term), Judge.alternate_email.ilike(term))).limit(25)
    return [{"id": str(j.id), "name": j.display_name, "email": j.primary_email or j.alternate_email, "do_not_contact": j.do_not_contact} for j in db.scalars(stmt.order_by(Judge.display_name))]


def unread_judges(db):
    return dict(db.execute(select(InboundMessage.judge_id, func.count()).where(InboundMessage.judge_id.is_not(None), InboundMessage.read_at.is_(None)).group_by(InboundMessage.judge_id)).all())


def competition_unread(db):
    # A reply associated with a campaign alerts only that competition. General judge
    # messages alert each active assignment until the judge's conversation is read.
    from .models import PilotNomination, PilotCompetition
    return dict(db.execute(select(PilotNomination.pilot_id, func.count(func.distinct(InboundMessage.id))).join(InboundMessage, (InboundMessage.judge_id == PilotNomination.judge_id) & or_(InboundMessage.competition_id == PilotNomination.pilot_id, InboundMessage.competition_id.is_(None))).join(PilotCompetition, PilotCompetition.id == PilotNomination.pilot_id).where(InboundMessage.read_at.is_(None), PilotCompetition.deleted_at.is_(None)).group_by(PilotNomination.pilot_id)).all())


@router.get("/conversations", response_model=Page)
def conversations(q: str = "", judge_id: UUID | None = None, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(25, ge=1, le=100), user=Depends(require("campaigns")), db=Depends(get_db)):
    incoming = select(InboundMessage.judge_id.label("judge_id"), func.max(InboundMessage.created_at).label("latest"), func.count().filter(InboundMessage.read_at.is_(None)).label("unread")).where(InboundMessage.judge_id.is_not(None)).group_by(InboundMessage.judge_id).subquery()
    outgoing = select(Recipient.judge_id.label("judge_id"), func.max(Recipient.sent_at).label("latest")).where(Recipient.sent_at.is_not(None), Recipient.judge_id.is_not(None)).group_by(Recipient.judge_id).subquery()
    stmt = select(Judge, incoming.c.latest, outgoing.c.latest, func.coalesce(incoming.c.unread, 0)).outerjoin(incoming, incoming.c.judge_id == Judge.id).outerjoin(outgoing, outgoing.c.judge_id == Judge.id).where(Judge.merged_into_id.is_(None), or_(incoming.c.latest.is_not(None), outgoing.c.latest.is_not(None)))
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Judge.display_name.ilike(term), Judge.primary_email.ilike(term)))
    if judge_id:
        stmt = stmt.where(Judge.id == judge_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(func.coalesce(incoming.c.unread, 0).desc(), func.greatest(incoming.c.latest, outgoing.c.latest).desc(), Judge.id).offset((page_no - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": str(j.id), "name": j.display_name, "email": j.primary_email or j.alternate_email, "unread_count": unread, "last_message_at": max([v for v in (received, sent) if v]).isoformat()} for j, received, sent, unread in rows], "total": total, "page": page_no, "page_size": page_size}


@router.get("/conversations/judges/{id}")
def conversation(id: UUID, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=100), user=Depends(require("campaigns")), db=Depends(get_db)):
    from .models import Outbound
    judge = get(db, Judge, id)
    incoming = select(InboundMessage.id, InboundMessage.created_at, literal("incoming").label("direction"), InboundMessage.sender_name.label("name"), InboundMessage.sender_email.label("email"), InboundMessage.subject, InboundMessage.body, InboundMessage.read_at, literal("received").label("status"), literal(None).label("campaign_id")).where(InboundMessage.judge_id == id)
    outgoing = select(Outbound.id, Outbound.created_at, literal("outgoing").label("direction"), Recipient.recipient_name.label("name"), Recipient.recipient_email.label("email"), Outbound.subject, Outbound.body_text.label("body"), literal(None).label("read_at"), Outbound.status, Recipient.campaign_id).join(Recipient, Recipient.id == Outbound.related_campaign_recipient_id).where(Recipient.judge_id == id)
    messages = union_all(incoming, outgoing).subquery()
    total = db.scalar(select(func.count()).select_from(messages))
    rows = db.execute(select(messages).order_by(messages.c.created_at.desc(), messages.c.id).offset((page_no - 1) * page_size).limit(page_size)).mappings().all()
    latest = db.scalar(select(func.max(InboundMessage.created_at)).where(InboundMessage.judge_id == id))
    return {"judge": {"id": str(judge.id), "name": judge.display_name, "email": judge.primary_email or judge.alternate_email, "phone": judge.phone, "notes": judge.notes}, "messages": [dict(row) for row in reversed(rows)], "total": total, "page": page_no, "page_size": page_size, "unread_count": unread_judges(db).get(id, 0), "read_through": latest}


@router.post("/conversations/judges/{id}/read")
def read_conversation(id: UUID, data: ConversationRead, user=Depends(require("campaigns")), db=Depends(get_db)):
    get(db, Judge, id)
    if data.read_through.tzinfo is None:
        fail("invalid_read_cursor", "A timezone is required for the read cursor.")
    cursor = min(data.read_through, now())
    db.execute(update(InboundMessage).where(InboundMessage.judge_id == id, InboundMessage.read_at.is_(None), InboundMessage.created_at <= cursor).values(read_at=now()))
    db.execute(update(Notification).where(Notification.judge_id == id, Notification.kind == "judge_reply", Notification.created_at <= cursor).values(read_at=now()))
    db.commit()
    return {"ok": True}


@router.post("/inbox/simulate")
def receive(data: IncomingEmail, user=Depends(require("campaigns")), db=Depends(get_db)):
    existing = db.scalar(select(InboundMessage).where(InboundMessage.request_id == data.request_id))
    if existing:
        return {"id": str(existing.id), "judge_id": str(existing.judge_id) if existing.judge_id else None, "ticket_id": str(existing.ticket_id) if existing.ticket_id else None}
    address = contact_email(data.sender_email)
    judge = db.scalar(select(Judge).where(Judge.merged_into_id.is_(None), or_(Judge.primary_email == address, Judge.alternate_email == address, Judge.preserved_emails.contains([address]))))
    recipient = None
    if data.campaign_recipient_id:
        recipient = get(db, Recipient, data.campaign_recipient_id)
        if recipient.recipient_email != address or recipient.status != "sent":
            fail("invalid_reply", "Choose a sent email addressed to this sender.")
        judge = db.get(Judge, recipient.judge_id) if recipient.judge_id else judge
    elif judge:
        recipient = db.scalar(select(Recipient).where(Recipient.judge_id == judge.id, Recipient.recipient_email == address, Recipient.status == "sent").order_by(Recipient.sent_at.desc()).limit(1))
    name = clean(data.sender_name).strip() or (judge.display_name if judge else address)
    message = InboundMessage(judge_id=judge.id if judge else None, campaign_recipient_id=recipient.id if recipient else None, sender_name=name, sender_email=address, subject=clean(data.subject), body=clean(data.body), request_id=data.request_id)
    db.add(message)
    if judge:
        campaign = db.get(Campaign, recipient.campaign_id) if recipient else None
        message.competition_id = campaign.pilot_competition_id if campaign else None
        db.flush()
        notification = notify(db, "judge_reply", f"{judge.display_name} replied", message.subject, f"/campaigns?judge={judge.id}", judge_id=judge.id)
        # The same timestamp lets the read cursor acknowledge the associated alert.
        notification.created_at = message.created_at
        href = f"/campaigns/conversations/judges/{judge.id}"
    else:
        from .tickets import ticket_scope
        possible = db.scalars(ticket_scope(user).where(Ticket.requester_email == address).order_by(Ticket.created_at.desc())).all()
        normalized = data.subject.removeprefix("Re: ").removeprefix("re: ").strip().casefold()
        ticket = next((t for t in possible if t.public_number in data.subject or t.subject.casefold() == normalized), None)
        if not ticket:
            number = db.scalar(select(ticket_sequence.next_value()))
            committee = db.scalar(select(Committee).where(Committee.name == "Competitions"))
            ticket = Ticket(public_number=f"MD-{number:06d}", requester_name=name, requester_email=address, subject=message.subject, committee_id=committee.id if committee else None, source="simulated_email", created_by=user.id)
            db.add(ticket)
            db.flush()
        else:
            ticket.last_message_at = now()
            ticket.status = "waiting_on_organizer"
            ticket.resolved_at, ticket.closed_at = None, None
        message.ticket_id = ticket.id
        db.add(TicketMessage(ticket_id=ticket.id, message_type="requester_message", sender_name=name, sender_email=address, body=message.body, created_by=user.id))
        notify(db, "ticket", f"Ticket email: {name}", message.subject, f"/tickets/{ticket.id}", ticket_id=ticket.id)
        href = f"/tickets/{ticket.id}"
    db.commit()
    return {"id": str(message.id), "judge_id": str(judge.id) if judge else None, "ticket_id": str(message.ticket_id) if message.ticket_id else None, "href": href}
