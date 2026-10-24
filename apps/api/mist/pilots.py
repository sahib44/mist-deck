"""Pilot competition workspace. Documents and contacts stay in the local database."""

import io
import json
import zipfile
from datetime import timedelta
from urllib.parse import quote
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from .auth import current_user, require, allowed, fail
from .competition_catalog import CATEGORIES
from .db import get_db, now
from .models import Judge, JudgeQualification, Qualification, PilotCompetition, PilotDocument, PilotNomination, User
from .schemas import ObjectView, Page, PilotJudgeIn, PilotStatusIn, PilotDeleteIn
from .services import (
    add_relations, audit, clean, contact_email, get, page, serialize, split_values,
    write_judge,
)

router = APIRouter(prefix="/api/competitions")
STATUSES = {"to_contact", "awaiting_response", "accepted", "declined"}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


def readable(user):
    if not allowed(user, "judges"):
        fail("forbidden", "Cannot view competitions.", 403)


def active_competition(db, id):
    competition = get(db, PilotCompetition, id)
    if competition.deleted_at:
        fail("not_found", "Competition not found.", 404)
    return competition


@router.get("/categories")
def categories(user=Depends(current_user), db=Depends(get_db)):
    readable(user)
    counts = dict(db.execute(
        select(PilotCompetition.category_slug, func.count())
        .where(PilotCompetition.deleted_at.is_(None))
        .group_by(PilotCompetition.category_slug)
    ).all())
    return [{"slug": slug, "name": name, "competition_count": counts.get(slug, 0)}
            for slug, (name, _) in CATEGORIES.items()]


@router.get("/deletions", response_model=Page)
def deleted_pilots(
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if not (allowed(user, "judges") or allowed(user, "audit")):
        fail("forbidden", "Cannot view deleted pilots.", 403)
    stmt = select(PilotCompetition).where(
        PilotCompetition.is_pilot.is_(True),
        PilotCompetition.deleted_at.is_not(None),
    ).order_by(PilotCompetition.deleted_at.desc())
    result = page(db, stmt, page_no, page_size)
    for item in result["items"]:
        actor = db.get(User, UUID(item["deleted_by"])) if item["deleted_by"] else None
        item["deleted_by_name"] = actor.full_name if actor else "Unknown organizer"
        item["category_name"] = CATEGORIES.get(item["category_slug"], (item["category_slug"], []))[0]
    return result


async def checked_document(upload, kind, user, pilot):
    if not upload or not upload.filename:
        return None
    name = upload.filename.replace("\\", "/").split("/")[-1].replace("\r", "").replace("\n", "")[:255]
    extension = name.lower().rsplit(".", 1)[-1]
    content = await upload.read(MAX_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        fail("invalid_document", "Rules and procedures must be nonempty and under 5 MB each.")
    if extension == "pdf" and content.startswith(b"%PDF-"):
        media_type = "application/pdf"
    elif extension == "docx" and content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as document:
                members = document.namelist()
                if "[Content_Types].xml" not in members or any("vbaProject" in x for x in members):
                    raise ValueError("Invalid DOCX")
        except (zipfile.BadZipFile, ValueError):
            fail("invalid_document", "Upload a valid PDF or non-macro DOCX file.")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        fail("invalid_document", "Upload a PDF or DOCX file for rules and procedures.")
    return PilotDocument(
        pilot_id=pilot.id,
        kind=kind,
        filename=name,
        media_type=media_type,
        content=content,
        uploaded_by=user.id,
    )


def pilot_view(db, pilot):
    data = serialize(pilot)
    data["counts"] = dict(
        db.execute(
            select(PilotNomination.status, func.count())
            .where(PilotNomination.pilot_id == pilot.id)
            .group_by(PilotNomination.status)
        ).all()
    )
    data["documents"] = [
        {"kind": doc.kind, "filename": doc.filename, "media_type": doc.media_type}
        for doc in db.scalars(
            select(PilotDocument).where(PilotDocument.pilot_id == pilot.id)
        )
    ]
    return data


@router.get("", response_model=Page)
def list_pilots(
    category_slug: str = "",
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    readable(user)
    if category_slug and category_slug not in CATEGORIES:
        fail("invalid_category", "Unknown competition category.")
    stmt = select(PilotCompetition).where(PilotCompetition.deleted_at.is_(None))
    if category_slug:
        stmt = stmt.where(PilotCompetition.category_slug == category_slug)
    return page(
        db,
        stmt.order_by(PilotCompetition.is_pilot, PilotCompetition.name),
        page_no,
        page_size,
        lambda pilot: pilot_view(db, pilot),
    )


@router.post("", response_model=ObjectView)
async def create_pilot(
    name: str = Form(...),
    event_year: int = Form(...),
    category_slug: str = Form(...),
    judge_ids: str = Form("[]"),
    rules: UploadFile | None = File(None),
    procedures: UploadFile | None = File(None),
    user=Depends(require("judges")),
    db=Depends(get_db),
):
    name = clean(name).strip()
    if not name or len(name) > 200 or not 2000 <= event_year <= 2200:
        fail("invalid_pilot", "Enter a name and an event year between 2000 and 2200.")
    if category_slug not in CATEGORIES:
        fail("invalid_category", "Choose a competition category.")
    if db.scalar(
        select(PilotCompetition).where(
            func.lower(PilotCompetition.name) == name.lower(),
            PilotCompetition.event_year == event_year,
            PilotCompetition.deleted_at.is_(None),
        )
    ):
        fail("duplicate_pilot", "A pilot with this name already exists for that year.", 409)
    try:
        ids = list(dict.fromkeys(UUID(str(x)) for x in json.loads(judge_ids)))
    except (TypeError, ValueError, json.JSONDecodeError):
        fail("invalid_judges", "Selected judges are invalid.")
    if len(ids) > 100:
        fail("invalid_judges", "Select at most 100 judges when creating a pilot.")
    judges = db.scalars(
        select(Judge).where(Judge.id.in_(ids), Judge.merged_into_id.is_(None))
    ).all()
    if len(judges) != len(ids):
        fail("invalid_judges", "One or more selected judges no longer exists.")
    pilot = PilotCompetition(name=name, event_year=event_year, category_slug=category_slug, is_pilot=True, created_by=user.id)
    db.add(pilot)
    db.flush()
    documents = [
        await checked_document(upload, kind, user, pilot)
        for kind, upload in (("rules", rules), ("procedures", procedures))
    ]
    db.add_all(doc for doc in documents if doc)
    db.add_all(PilotNomination(pilot_id=pilot.id, judge_id=judge.id) for judge in judges)
    audit(db, user, "pilot.created", pilot, f"Created pilot {name}")
    db.commit()
    return pilot_view(db, pilot)


@router.get("/{id}", response_model=ObjectView)
def pilot_detail(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    readable(user)
    return pilot_view(db, active_competition(db, id))


@router.delete("/{id}", response_model=ObjectView)
def delete_pilot(id: UUID, data: PilotDeleteIn, user=Depends(require("judges")), db=Depends(get_db)):
    pilot = active_competition(db, id)
    if not pilot.is_pilot:
        fail("permanent_competition", "Permanent competitions cannot be deleted.", 403)
    if not data.confirmed_first or not data.confirmed_second or data.exact_name != pilot.name:
        fail("delete_confirmation", "Complete all three deletion confirmations.", 400)
    before = serialize(pilot)
    pilot.deleted_at = now()
    pilot.deleted_by = user.id
    audit(db, user, "pilot.deleted", pilot, f"Deleted pilot {pilot.name}", before, serialize(pilot))
    db.commit()
    return {"id": str(pilot.id)}


@router.get("/{id}/documents/{kind}")
def download_document(
    id: UUID, kind: str, user=Depends(current_user), db=Depends(get_db)
):
    readable(user)
    active_competition(db, id)
    if kind not in {"rules", "procedures"}:
        fail("not_found", "Unknown document.", 404)
    doc = db.scalar(
        select(PilotDocument).where(
            PilotDocument.pilot_id == id, PilotDocument.kind == kind
        )
    )
    if not doc:
        fail("not_found", "Document not found.", 404)
    disposition = "inline" if doc.media_type == "application/pdf" else "attachment"
    return Response(
        doc.content,
        media_type=doc.media_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(doc.filename)}"},
    )


@router.put("/{id}/documents/{kind}", response_model=ObjectView)
async def upload_document(
    id: UUID,
    kind: str,
    file: UploadFile = File(...),
    user=Depends(require("judges")),
    db=Depends(get_db),
):
    if kind not in {"rules", "procedures"}:
        fail("not_found", "Unknown document.", 404)
    pilot = active_competition(db, id)
    incoming = await checked_document(file, kind, user, pilot)
    if not incoming:
        fail("invalid_document", "Choose a PDF or DOCX file.")
    existing = db.scalar(
        select(PilotDocument).where(
            PilotDocument.pilot_id == id, PilotDocument.kind == kind
        )
    )
    if existing:
        existing.filename = incoming.filename
        existing.media_type = incoming.media_type
        existing.content = incoming.content
        existing.uploaded_by = user.id
        document = existing
    else:
        db.add(incoming)
        document = incoming
    audit(db, user, "pilot.document_uploaded", pilot, f"Updated {kind} document")
    db.commit()
    return {"id": str(document.id), "kind": kind, "filename": document.filename}


@router.get("/{id}/judges", response_model=Page)
def pilot_judges(
    id: UUID,
    status: str = "",
    q: str = "",
    overdue_days: int | None = Query(None, ge=1, le=365),
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    readable(user)
    active_competition(db, id)
    if status and status not in STATUSES:
        fail("invalid_status", "Unknown nomination status.")
    stmt = select(PilotNomination).where(PilotNomination.pilot_id == id)
    if status:
        stmt = stmt.where(PilotNomination.status == status)
    if q.strip():
        stmt = stmt.join(Judge).where(
            or_(
                Judge.display_name.ilike(f"%{q.strip()}%"),
                Judge.primary_email.ilike(f"%{q.strip()}%"),
            )
        )
    if overdue_days:
        stmt = stmt.where(
            PilotNomination.status == "awaiting_response",
            PilotNomination.last_contacted_at <= now() - timedelta(days=overdue_days),
        )
    stmt = stmt.order_by(PilotNomination.created_at.desc())

    def view(nomination):
        judge = get(db, Judge, nomination.judge_id)
        return {
            **serialize(nomination),
            "judge": {
                "id": str(judge.id),
                "display_name": judge.display_name,
                "primary_email": judge.primary_email,
                "phone": judge.phone,
                "do_not_contact": judge.do_not_contact,
                "qualification_text": nomination.qualification_text,
                "qualifications": [
                    name for (name,) in db.execute(
                        select(Qualification.name)
                        .join(JudgeQualification)
                        .where(JudgeQualification.judge_id == judge.id)
                    )
                ],
            },
        }

    return page(db, stmt, page_no, page_size, view)


@router.post("/{id}/judges", response_model=ObjectView)
def add_pilot_judge(
    id: UUID,
    data: PilotJudgeIn,
    user=Depends(require("judges")),
    db=Depends(get_db),
):
    pilot = active_competition(db, id)
    if data.existing_judge_id:
        judge = get(db, Judge, data.existing_judge_id)
        if judge.merged_into_id:
            fail("invalid_judge", "Use an active judge contact.")
    else:
        name = clean(data.name).strip()
        address = contact_email(data.email, optional=True)
        phone = clean(data.phone).strip()
        if not name or not (address or phone):
            fail("contact_required", "Enter a name and at least an email or phone.")
        judge = db.scalar(
            select(Judge).where(Judge.primary_email == address, Judge.merged_into_id.is_(None))
        ) if address else None
        if judge:
            if name.casefold() != judge.display_name.casefold():
                fail("existing_contact", "This email belongs to an existing judge. Select that contact instead.", 409)
            if phone and not judge.phone:
                judge.phone = phone
        else:
            first, _, last = name.partition(" ")
            judge = write_judge(
                db,
                {
                    "display_name": name,
                    "first_name": first,
                    "last_name": last,
                    "primary_email": address,
                    "phone": phone,
                    "qualifications": [],
                },
                user,
                source=f"pilot {pilot.id}",
            )
    if db.scalar(
        select(PilotNomination).where(
            PilotNomination.pilot_id == id, PilotNomination.judge_id == judge.id
        )
    ):
        fail("already_added", "This judge is already in the pilot.", 409)
    nomination = PilotNomination(
        pilot_id=id, judge_id=judge.id,
        qualification_text=clean(data.qualifications).strip(),
    )
    db.add(nomination)
    audit(db, user, "pilot.judge_added", nomination, "Judge added to pilot")
    db.commit()
    return serialize(nomination)


@router.patch("/{id}/judges/{nomination_id}", response_model=ObjectView)
def set_pilot_status(
    id: UUID,
    nomination_id: UUID,
    data: PilotStatusIn,
    user=Depends(require("judges")),
    db=Depends(get_db),
):
    active_competition(db, id)
    nomination = get(db, PilotNomination, nomination_id, True)
    if nomination.pilot_id != id:
        fail("not_found", "Nomination not found in this pilot.", 404)
    before = serialize(nomination)
    previous_status = nomination.status
    nomination.status = data.status
    nomination.responded_at = now() if data.status in {"accepted", "declined"} else None
    if data.status == "awaiting_response" and previous_status != "awaiting_response":
        nomination.last_contacted_at = now()
    audit(db, user, "pilot.response_updated", nomination, f"Judge response: {data.status}", before, serialize(nomination))
    db.commit()
    return serialize(nomination)
