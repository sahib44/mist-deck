"""Competition-oriented judge directory and spreadsheet export."""

import csv
import io
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, case, func, or_, select
from .auth import allowed, current_user, fail
from .competition_catalog import CATEGORIES
from .db import get_db
from .models import Judge, PilotCompetition, PilotNomination
from .schemas import Page
from .services import judge_views

router = APIRouter(prefix="/api/judge-directory")


def readable(user):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot view judge directory.", 403)


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
        stmt = stmt.where(func.coalesce(PilotNomination.status, "to_contact") == status)
    return stmt


def view_rows(db, rows):
    judges = {judge.id: judge for judge, _, _ in rows}
    legacy = {item["id"]: item for item in judge_views(db, list(judges.values()))}
    result = []
    for judge, nomination, competition in rows:
        fallback = "; ".join(legacy[str(judge.id)]["qualifications"])
        result.append({
            "id": str(nomination.id) if nomination else str(judge.id),
            "judge_id": str(judge.id),
            "name": judge.display_name,
            "email": judge.primary_email or judge.alternate_email,
            "phone": judge.phone,
            "contact": " · ".join(v for v in (judge.primary_email or judge.alternate_email, judge.phone) if v),
            "qualification": nomination.qualification_text or fallback if nomination else fallback,
            "status": nomination.status if nomination else "to_contact",
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
    return {"items": view_rows(db, rows), "total": total, "page": page_no, "page_size": page_size}


def spreadsheet_cell(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.get("/export")
def export_directory(
    q: str = "", category_slug: str = "", competition_id: UUID | None = None, status: str = "",
    user=Depends(current_user), db=Depends(get_db),
):
    readable(user)
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
    return Response(
        "\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mist-deck-judges.csv"},
    )
