from uuid import UUID, uuid4
from urllib.parse import quote
import io
import zipfile
from fastapi import APIRouter, Depends, Query, File, UploadFile, Response
from sqlalchemy import select, func
from .db import get_db, now
from .models import *
from .schemas import CampaignIn, ForwardIn, ObjectView, Page, Failure
from .auth import require, current_user, allowed, fail
from .services import *

router = APIRouter(prefix="/api")
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_CAMPAIGN_ATTACHMENTS = 5


def attachment_type(name, content):
    ext = name.lower().rsplit(".", 1)[-1]
    if ext == "pdf" and content.startswith(b"%PDF-"):
        return "application/pdf"
    if ext == "png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if ext in {"jpg", "jpeg"} and content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if ext == "docx" and content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as document:
                names = document.namelist()
                if "[Content_Types].xml" in names and not any("vbaProject" in x for x in names):
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            pass
    if ext in {"txt", "csv"}:
        try:
            content.decode("utf-8")
            return "text/plain" if ext == "txt" else "text/csv"
        except UnicodeDecodeError:
            pass
    fail("invalid_attachment", "Use a valid PDF, DOCX, PNG, JPG, TXT, or CSV file.")


def attachments_for(db, campaign_id):
    if not campaign_id:
        return []
    return [
        {"id": str(file.id), "filename": file.filename, "media_type": file.media_type, "size": len(file.content)}
        for file in db.scalars(select(CampaignAttachment).where(CampaignAttachment.campaign_id == campaign_id).order_by(CampaignAttachment.created_at))
    ]


def source_campaign_id(db, message):
    seen = set()
    while message and message.id not in seen:
        seen.add(message.id)
        if message.related_campaign_recipient_id:
            recipient = db.get(Recipient, message.related_campaign_recipient_id)
            return recipient.campaign_id if recipient else None
        message = db.get(Outbound, message.forwarded_from_id) if message.forwarded_from_id else None
    return None


@router.get("/campaigns", response_model=Page)
def campaigns(
    status: str = "",
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(require("campaigns")),
    db=Depends(get_db),
):
    stmt = select(Campaign).order_by(Campaign.created_at.desc())
    if status:
        stmt = stmt.where(Campaign.status == status)
    return page(db, stmt, page_no, page_size)


@router.post("/campaigns", response_model=ObjectView)
def create(data: CampaignIn, user=Depends(require("campaigns")), db=Depends(get_db)):
    render_template(data.subject_template, {})
    render_template(data.body_template, {})
    if set(data.variables) - TEMPLATE_VARS:
        fail("unknown_template_variable", "Unsupported event variable.")
    pilot = get(db, PilotCompetition, data.pilot_competition_id) if data.pilot_competition_id else None
    if pilot and pilot.deleted_at:
        fail("not_found", "Competition not found.", 404)
    if pilot and data.saved_list_id:
        fail("invalid_recipients", "Choose judges from the pilot, not a saved list.")
    pilot_nominations = {}
    if pilot:
        pilot_nominations = {
            n.judge_id: n for n in db.scalars(
                select(PilotNomination).where(
                    PilotNomination.pilot_id == pilot.id,
                    PilotNomination.judge_id.in_(data.judge_ids),
                )
            )
        }
        if not data.judge_ids or len(pilot_nominations) != len(set(data.judge_ids)):
            fail("invalid_recipients", "Select judges who belong to this pilot.")
    stmt = (
        judge_query(get(db, SavedList, data.saved_list_id).filter_definition)
        if data.saved_list_id
        else select(Judge).where(
            Judge.id.in_(data.judge_ids), Judge.merged_into_id.is_(None)
        )
    )
    judges = db.scalars(stmt).all()
    if len(judges) > 5000:
        fail("recipient_limit", "Limit each campaign to 5000 contacts.")
    campaign = Campaign(
        name=clean(data.name),
        subject_template=clean(data.subject_template),
        body_template=clean(data.body_template),
        variables=data.variables,
        created_by=user.id,
        pilot_competition_id=pilot.id if pilot else None,
    )
    db.add(campaign)
    db.flush()
    excluded, seen = [], set()
    for judge in judge_views(db, judges):
        reason = ""
        if judge["do_not_contact"]:
            reason = "Do not contact"
        if pilot and pilot_nominations[UUID(judge["id"])].status == "declined":
            reason = "Declined this pilot"
        try:
            address = (
                contact_email(judge["primary_email"])
                if pilot else safe_email(judge["primary_email"])
            )
        except Exception:
            reason = "Missing or invalid email"
            address = ""
        if address in seen:
            reason = "Duplicate normalized email"
        if reason:
            excluded.append({"judge_name": judge["display_name"], "reason": reason})
            continue
        seen.add(address)
        values = {
            **data.variables,
            "judge_name": judge["display_name"],
            "first_name": judge["first_name"],
            "organization": judge["organization"],
            "category_name": pilot.name if pilot else ", ".join(judge["categories"]),
        }
        db.add(
            Recipient(
                campaign_id=campaign.id,
                judge_id=UUID(judge["id"]),
                recipient_email=address,
                rendered_subject=render_template(data.subject_template, values),
                rendered_body=render_template(data.body_template, values),
            )
        )
    if not seen:
        fail(
            "no_recipients",
            "No eligible recipients with email addresses remain.",
        )
    audit(
        db,
        user,
        "campaign.created",
        campaign,
        f"Created campaign with {len(seen)} recipients",
    )
    db.commit()
    return {**serialize(campaign), "recipient_count": len(seen), "excluded": excluded}


@router.get("/campaigns/{id}", response_model=ObjectView)
def campaign(id: UUID, user=Depends(require("campaigns")), db=Depends(get_db)):
    result = serialize(get(db, Campaign, id))
    result["recipient_count"] = db.scalar(
        select(func.count()).select_from(Recipient).where(Recipient.campaign_id == id)
    )
    result["counts"] = dict(
        db.execute(
            select(Recipient.status, func.count())
            .where(Recipient.campaign_id == id)
            .group_by(Recipient.status)
        ).all()
    )
    result["attachments"] = attachments_for(db, id)
    return result


@router.post("/campaigns/{id}/attachments", response_model=ObjectView)
async def upload_campaign_attachment(
    id: UUID,
    file: UploadFile = File(...),
    user=Depends(require("campaigns")),
    db=Depends(get_db),
):
    campaign = get(db, Campaign, id, True)
    if campaign.status != "draft":
        fail("invalid_state", "Attachments can only be changed while the campaign is a draft.")
    count = db.scalar(select(func.count()).select_from(CampaignAttachment).where(CampaignAttachment.campaign_id == id))
    if count >= MAX_CAMPAIGN_ATTACHMENTS:
        fail("attachment_limit", "A campaign can have at most five attachments.")
    name = file.filename.replace("\\", "/").split("/")[-1].replace("\r", "").replace("\n", "")[:255] if file.filename else ""
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if not name or not content or len(content) > MAX_ATTACHMENT_BYTES:
        fail("invalid_attachment", "Choose a nonempty file under 5 MB.")
    media_type = attachment_type(name, content)
    item = CampaignAttachment(campaign_id=id, filename=name, media_type=media_type, content=content, uploaded_by=user.id)
    db.add(item)
    audit(db, user, "campaign.attachment_added", campaign, f"Attached {name} to campaign")
    db.commit()
    return {"id": str(item.id), "filename": name, "media_type": media_type, "size": len(content)}


@router.delete("/campaigns/{id}/attachments/{attachment_id}", response_model=ObjectView)
def delete_campaign_attachment(id: UUID, attachment_id: UUID, user=Depends(require("campaigns")), db=Depends(get_db)):
    campaign = get(db, Campaign, id, True)
    if campaign.status != "draft":
        fail("invalid_state", "Attachments can only be changed while the campaign is a draft.")
    item = get(db, CampaignAttachment, attachment_id)
    if item.campaign_id != id:
        fail("not_found", "Attachment not found.", 404)
    db.delete(item)
    audit(db, user, "campaign.attachment_removed", campaign, f"Removed {item.filename} from campaign")
    db.commit()
    return {"id": str(attachment_id)}


@router.get("/campaigns/{id}/attachments/{attachment_id}")
def download_campaign_attachment(id: UUID, attachment_id: UUID, user=Depends(require("campaigns")), db=Depends(get_db)):
    get(db, Campaign, id)
    item = db.get(CampaignAttachment, attachment_id)
    if not item or item.campaign_id != id:
        fail("not_found", "Attachment not found.", 404)
    return Response(
        item.content, media_type=item.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.filename)}"},
    )


@router.get("/campaigns/{id}/preview", response_model=Page)
def preview(
    id: UUID,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(require("campaigns")),
    db=Depends(get_db),
):
    get(db, Campaign, id)
    return page(
        db,
        select(Recipient)
        .where(Recipient.campaign_id == id)
        .order_by(Recipient.recipient_email),
        page_no,
        page_size,
    )


@router.post("/campaigns/{id}/{action}", response_model=ObjectView)
def transition(
    id: UUID, action: str, user=Depends(require("campaigns")), db=Depends(get_db)
):
    campaign = get(db, Campaign, id, True)
    before = serialize(campaign)
    required = {"submit": "draft", "approve": "pending_approval", "queue": "approved"}
    if action == "cancel":
        if not allowed(user, "approve"):
            fail(
                "forbidden", "Campaign cancellation requires approval permission.", 403
            )
        if campaign.status in {"completed", "cancelled", "partially_failed"}:
            fail("invalid_state", "Campaign is already terminal.")
        campaign.status = "cancelled"
        recipients = db.scalars(
            select(Recipient).where(Recipient.campaign_id == id)
        ).all()
        ids = [r.id for r in recipients]
        for msg in db.scalars(
            select(Outbound)
            .where(Outbound.related_campaign_recipient_id.in_(ids))
            .with_for_update()
        ):
            if msg.status != "sent":
                msg.status = "cancelled"
        for rec in recipients:
            if rec.status != "sent":
                rec.status = "cancelled"
    elif action in required:
        if campaign.status != required[action]:
            if action == "queue" and campaign.status in {
                "queued",
                "sending",
                "completed",
                "partially_failed",
            }:
                return serialize(campaign)
            fail("invalid_state", f"{action} requires {required[action]} status.")
        if action == "submit":
            campaign.status = "pending_approval"
        elif action == "approve":
            if not allowed(user, "approve"):
                fail("forbidden", "Campaign approval permission is required.", 403)
            campaign.status, campaign.approved_by, campaign.approved_at = (
                "approved",
                user.id,
                now(),
            )
        elif action == "queue":
            for rec in db.scalars(select(Recipient).where(Recipient.campaign_id == id)):
                judge = get(db, Judge, rec.judge_id)
                if judge.do_not_contact or judge.merged_into_id:
                    rec.status, rec.failure_reason = (
                        "cancelled",
                        "Contact is now suppressed or merged",
                    )
                    continue
                if campaign.pilot_competition_id:
                    contact_email(rec.recipient_email)
                else:
                    safe_email(rec.recipient_email)
                db.add(
                    Outbound(
                        recipient_email=rec.recipient_email,
                        recipient_name=judge.display_name,
                        subject=rec.rendered_subject,
                        body_text=rec.rendered_body,
                        related_campaign_recipient_id=rec.id,
                        idempotency_key=f"campaign:{rec.id}",
                    )
                )
                rec.status = "queued"
            campaign.status = "queued"
            db.flush()
            from .worker import aggregate

            aggregate(db, campaign)
    else:
        fail("not_found", "Unknown campaign action.", 404)
    audit(
        db,
        user,
        f"campaign.{action}",
        campaign,
        f"Campaign {action}",
        before,
        serialize(campaign),
    )
    db.commit()
    return serialize(campaign)


def outbox_scope(user):
    stmt = select(Outbound)
    if (
        user.role == "technology_administrator"
        and "private_tickets" not in user.permissions
    ):
        stmt = stmt.where(Outbound.related_ticket_id.is_(None))
    elif user.role == "competitions_administrator":
        from .tickets import ticket_scope

        stmt = stmt.where(
            or_(
                Outbound.related_ticket_id.is_(None),
                Outbound.related_ticket_id.in_(
                    ticket_scope(user).with_only_columns(Ticket.id)
                ),
            )
        )
    return stmt


@router.get("/outbox", response_model=Page)
def outbox(
    status: str = "",
    q: str = "",
    campaign_id: UUID | None = None,
    ticket_id: UUID | None = None,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(require("outbox")),
    db=Depends(get_db),
):
    stmt = outbox_scope(user).order_by(Outbound.created_at.desc())
    if status:
        stmt = stmt.where(Outbound.status == status)
    if q:
        stmt = stmt.where(
            or_(
                Outbound.recipient_email.ilike(f"%{q}%"),
                Outbound.subject.ilike(f"%{q}%"),
            )
        )
    if campaign_id:
        stmt = stmt.where(
            Outbound.related_campaign_recipient_id.in_(
                select(Recipient.id).where(Recipient.campaign_id == campaign_id)
            )
        )
    if ticket_id:
        stmt = stmt.where(Outbound.related_ticket_id == ticket_id)
    result = page(db, stmt, page_no, page_size)
    for item in result["items"]:
        item["attachments"] = attachments_for(db, source_campaign_id(db, db.get(Outbound, UUID(item["id"]))))
    return result


@router.get("/outbox/{id}/attachments/{attachment_id}")
def download_outbox_attachment(id: UUID, attachment_id: UUID, user=Depends(require("outbox")), db=Depends(get_db)):
    message = db.scalar(outbox_scope(user).where(Outbound.id == id))
    if not message:
        fail("not_found", "Message not found.", 404)
    campaign_id = source_campaign_id(db, message)
    item = db.get(CampaignAttachment, attachment_id)
    if not item or item.campaign_id != campaign_id:
        fail("not_found", "Attachment not found.", 404)
    return Response(
        item.content,
        media_type=item.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.filename)}"},
    )


@router.post("/outbox/{id}/forward", response_model=ObjectView)
def forward_message(id: UUID, data: ForwardIn, user=Depends(require("outbox")), db=Depends(get_db)):
    original = db.scalar(outbox_scope(user).where(Outbound.id == id))
    if not original or original.status != "sent":
        fail("invalid_forward", "Only sent sandbox messages can be forwarded.", 400)
    address = contact_email(data.recipient_email)
    note = clean(data.note).strip()
    subject = original.subject if original.subject.lower().startswith("fwd:") else f"Fwd: {original.subject}"
    body = f"{note}\n\n" if note else ""
    body += f"---------- Forwarded message ----------\nTo: {original.recipient_email}\nSubject: {original.subject}\n\n{original.body_text}"
    forwarded = Outbound(
        recipient_email=address, recipient_name=address, subject=subject, body_text=body,
        forwarded_from_id=original.id, idempotency_key=f"forward:{uuid4()}",
    )
    db.add(forwarded)
    audit(db, user, "message.forwarded", forwarded, "Queued a sandbox forward", after={"forwarded_from_id": str(id), "recipient_email": address})
    db.commit()
    return {**serialize(forwarded), "attachments": attachments_for(db, source_campaign_id(db, original))}


@router.post("/outbox/{id}/failure", response_model=ObjectView)
def failure(id: UUID, data: Failure, user=Depends(require("jobs")), db=Depends(get_db)):
    item = db.scalar(outbox_scope(user).where(Outbound.id == id).with_for_update())
    if not item:
        fail("not_found", "Message not found.", 404)
    if item.status not in {"queued", "failed"}:
        fail(
            "invalid_state",
            "Failure simulation can only change queued or failed messages.",
        )
    item.simulate_failure = data.enabled
    audit(
        db,
        user,
        "message.failure_simulation",
        item,
        f"Failure simulation: {data.enabled}",
    )
    db.commit()
    return serialize(item)


@router.post("/outbox/{id}/retry", response_model=ObjectView)
def retry(id: UUID, user=Depends(require("jobs")), db=Depends(get_db)):
    initial = db.scalar(outbox_scope(user).where(Outbound.id == id))
    if not initial:
        fail("not_found", "Message not found.", 404)
    if initial.related_campaign_recipient_id:
        initial_rec = get(db, Recipient, initial.related_campaign_recipient_id)
        get(db, Campaign, initial_rec.campaign_id, True)
    item = db.scalar(
        outbox_scope(user)
        .where(Outbound.id == id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item.status != "failed":
        fail("invalid_state", "Only failed messages can be retried.")
    if item.related_campaign_recipient_id:
        rec = get(db, Recipient, item.related_campaign_recipient_id)
        campaign = get(db, Campaign, rec.campaign_id)
        if campaign.status == "cancelled":
            fail("cancelled", "Cancelled campaigns cannot be retried.")
        rec.status, campaign.status = "queued", "queued"
    item.status, item.attempt_count, item.available_at, item.last_error = (
        "queued",
        0,
        now(),
        "",
    )
    audit(
        db,
        user,
        "message.retry",
        item,
        "Administrator started a new bounded retry cycle",
    )
    db.commit()
    return serialize(item)
