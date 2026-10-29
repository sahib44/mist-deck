"""Competition-oriented judge directory and spreadsheet export."""

import csv
import io
import hashlib
import json
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, case, func, or_, select, update, delete, text
from .auth import allowed, current_user, fail, require, hasher
from argon2.exceptions import VerificationError
from .competition_catalog import CATEGORIES
from .db import get_db, now
from .models import *
from .schemas import Page, ClearJudges, PilotStatusIn
from .services import judge_views, serialize, audit

router = APIRouter(prefix="/api/judge-directory")


def readable(user):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot view judge directory.", 403)


def response_status(value):
    return {"prospective": "to_contact", "contacted": "awaiting_response", "interested": "accepted", "confirmed": "accepted", "inactive": "declined"}.get(value, value)


def directory_query(q="", category_slug="", competition_id=None, status=""):
    active_ids = select(PilotCompetition.id).where(PilotCompetition.deleted_at.is_(None))
    stmt = (
        select(Judge, PilotNomination, PilotCompetition)
        .select_from(Judge)
        .outerjoin(PilotNomination, and_(
            PilotNomination.judge_id == Judge.id,
            PilotNomination.pilot_id.in_(active_ids),
        ))
        .outerjoin(PilotCompetition, PilotCompetition.id == PilotNomination.pilot_id)
        .where(Judge.merged_into_id.is_(None))
    )
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Judge.display_name.ilike(term), Judge.primary_email.ilike(term), Judge.phone.ilike(term), PilotCompetition.name.ilike(term)))
    if category_slug:
        stmt = stmt.where(PilotCompetition.category_slug == category_slug)
    if competition_id:
        stmt = stmt.where(PilotCompetition.id == competition_id)
    if status:
        if status not in {"to_contact", "awaiting_response", "accepted", "declined"}:
            fail("invalid_status", "Unknown judge response.")
        stmt = stmt.where(func.coalesce(PilotNomination.status, case({"prospective": "to_contact", "contacted": "awaiting_response", "interested": "accepted", "confirmed": "accepted", "inactive": "declined"}, value=Judge.status, else_=Judge.status)) == status)
    return stmt


def view_rows(db, rows):
    judges = {judge.id: judge for judge, _, _ in rows}
    legacy = {item["id"]: item for item in judge_views(db, list(judges.values()))}
    result = []
    for judge, nomination, competition in rows:
        fallback = judge.notes or "; ".join(legacy[str(judge.id)]["qualifications"])
        result.append({
            "id": str(nomination.id) if nomination else str(judge.id),
            "judge_id": str(judge.id),
            "name": judge.display_name,
            "email": judge.primary_email or judge.alternate_email,
            "phone": judge.phone,
            "contact": " · ".join(v for v in (judge.primary_email or judge.alternate_email, judge.phone) if v),
            "qualification": nomination.qualification_text or fallback if nomination else fallback,
            "status": nomination.status if nomination else response_status(judge.status),
            "category_slug": competition.category_slug if competition else "",
            "category": CATEGORIES[competition.category_slug][0] if competition and competition.category_slug in CATEGORIES else "Unassigned",
            "competition_id": str(competition.id) if competition else None,
            "competition": competition.name if competition else "Unassigned",
            "event_year": competition.event_year if competition else None,
            "added_at": (nomination.created_at if nomination else judge.created_at).isoformat(),
        })
    return result


@router.get("", response_model=Page)
def directory(
    q: str = "", category_slug: str = "", competition_id: UUID | None = None, status: str = "",
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user), db=Depends(get_db),
):
    readable(user)
    stmt = directory_query(q, category_slug, competition_id, status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(
        func.coalesce(PilotNomination.created_at, Judge.created_at), Judge.id,
    ).offset((page_no - 1) * page_size).limit(page_size)).all()
    from .inbox import unread_judges
    unread = unread_judges(db)
    items = view_rows(db, rows)
    for item in items:
        item["unread_count"] = unread.get(UUID(item["judge_id"]), 0)
    return {"items": items, "total": total, "page": page_no, "page_size": page_size}


def spreadsheet_cell(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.get("/export")
def export_directory(
    q: str = "", category_slug: str = "", competition_id: UUID | None = None, status: str = "",
    user=Depends(current_user), db=Depends(get_db),
):
    readable(user)
    return Response(sheet_content(db, q, category_slug, competition_id, status), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=mist-deck-judges.csv"})


def sheet_content(db, q="", category_slug="", competition_id=None, status=""):
    category_order = case(
        {slug: index for index, slug in enumerate(CATEGORIES)},
        value=PilotCompetition.category_slug,
        else_=len(CATEGORIES),
    )
    competition_order = case(
        {name: index for _, names in CATEGORIES.values() for index, name in enumerate(names)},
        value=PilotCompetition.name, else_=999,
    )
    rows = db.execute(directory_query(q, category_slug, competition_id, status).order_by(
        category_order, PilotCompetition.is_pilot, competition_order, PilotCompetition.name,
        func.coalesce(PilotNomination.created_at, Judge.created_at), Judge.id,
    )).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Main category", "Competition", "Response", "Name", "Contact", "Qualification", "Year", "Added"])
    for item in view_rows(db, rows):
        writer.writerow([spreadsheet_cell(item[key]) for key in (
            "category", "competition", "status", "name", "contact", "qualification", "event_year", "added_at",
        )])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def directory_fingerprint(db):
    records = {cls.__tablename__: [serialize(item) for item in db.scalars(select(cls).order_by(cls.id))] for cls in (Judge, PilotNomination, PilotCompetition)}
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


@router.patch("/{id}/status")
def set_unassigned_status(id: UUID, data: PilotStatusIn, user=Depends(require("judges")), db=Depends(get_db)):
    judge = db.get(Judge, id)
    if not judge or judge.merged_into_id:
        fail("not_found", "Judge not found.", 404)
    judge.status = data.status
    audit(db, user, "judge.response_updated", judge, f"Judge response: {data.status}")
    db.commit()
    return {"id": str(id)}


@router.post("/clear/prepare")
def prepare_clear(user=Depends(require("delete")), db=Depends(get_db)):
    db.execute(text("LOCK TABLE judge_contacts, pilot_nominations, pilot_competitions IN SHARE ROW EXCLUSIVE MODE"))
    backup = DirectoryBackup(created_by=user.id, content=sheet_content(db), fingerprint=directory_fingerprint(db), judge_count=db.scalar(select(func.count()).select_from(Judge)))
    db.add(backup)
    db.commit()
    return {"id": str(backup.id), "judge_count": backup.judge_count, "download_url": f"/api/judge-directory/backups/{backup.id}"}


@router.get("/backups/{id}")
def download_backup(id: UUID, user=Depends(require("delete")), db=Depends(get_db)):
    backup = db.get(DirectoryBackup, id)
    if not backup:
        fail("not_found", "Backup not found.", 404)
    return Response(backup.content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=mist-deck-judges-backup-{backup.created_at:%Y%m%d-%H%M%S}.csv"})


@router.post("/clear")
def clear_directory(data: ClearJudges, user=Depends(require("delete")), db=Depends(get_db)):
    if not data.confirmed_first or not data.confirmed_second:
        fail("delete_confirmation", "Complete all three confirmations.")
    try:
        hasher.verify(user.password_hash, data.password)
    except VerificationError:
        fail("invalid_password", "Your password is incorrect.", 403)
    backup = db.scalar(select(DirectoryBackup).where(DirectoryBackup.id == data.backup_id).with_for_update())
    if not backup or backup.created_by != user.id or backup.cleared_at or backup.created_at < now() - timedelta(minutes=15):
        fail("backup_required", "Create a fresh sheet backup before clearing judges.")
    # Prevent contact edits and new assignments between validation and deletion.
    db.execute(text("LOCK TABLE judge_contacts, pilot_nominations, pilot_competitions IN SHARE ROW EXCLUSIVE MODE"))
    if backup.fingerprint != directory_fingerprint(db):
        fail("directory_changed", "The directory changed. Cancel and restart to export a fresh backup.", 409)
    count = backup.judge_count
    db.execute(update(Recipient).values(judge_id=None))
    db.execute(update(ImportRow).values(matched_judge_id=None))
    db.execute(update(Duplicate).values(existing_judge_id=None))
    db.execute(update(Notification).where(Notification.kind == "judge_reply").values(read_at=now(), href="/campaigns"))
    for cls in (MergeEvent, PilotNomination, Engagement, JudgeCategory, JudgeQualification):
        db.execute(delete(cls))
    db.execute(update(Judge).values(merged_into_id=None))
    db.execute(delete(Judge))
    backup.cleared_at = now()
    audit(db, user, "judges.cleared", backup, f"Cleared {count} judge contacts after saving sheet backup", after={"backup_id": str(backup.id), "judge_count": count})
    db.commit()
    return {"cleared": count, "backup_url": f"/api/judge-directory/backups/{backup.id}"}
