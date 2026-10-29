import hashlib
import logging
import time
from uuid import UUID
from fastapi import FastAPI, Depends, Request, Response, Query
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, delete, text, func
from sqlalchemy.exc import IntegrityError
from .db import get_db, now
from .models import *
from .schemas import *
from . import schemas as s
from .auth import current_user, require, allowed, login, fail
from .services import *

app = FastAPI(title="MIST Deck", version="1.2.0")
logger = logging.getLogger("mist")


@app.middleware("http")
async def request_log(request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.monotonic() - started) * 1000),
        }
    )
    return response


@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "validation_error",
                "message": "; ".join(
                    f'{".".join(map(str,e["loc"]))}: {e["msg"]}' for e in exc.errors()
                ),
            }
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "conflict",
                "message": "A record with these values already exists, or a linked record changed. Refresh and try again.",
            }
        },
    )


@app.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "email_provider": "mock"}


@app.post("/api/auth/login", response_model=UserView)
def sign_in(data: Login, response: Response, db=Depends(get_db)):
    return login(db, data.email, data.password, response)


@app.get("/api/auth/me", response_model=UserView)
def me(user=Depends(current_user)):
    return user


@app.post("/api/auth/logout")
def logout(
    request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)
):
    db.execute(
        delete(Session).where(
            Session.token_hash
            == hashlib.sha256(
                request.cookies.get("mist_session", "").encode()
            ).hexdigest()
        )
    )
    db.commit()
    response.delete_cookie("mist_session")
    return {"ok": True}


@app.get("/api/users", response_model=Page)
def users(
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if not (
        allowed(user, "users")
        or allowed(user, "tickets")
        or "private_tickets" in user.permissions
    ):
        fail("forbidden", "Cannot view users.", 403)
    return page(
        db,
        select(User).order_by(User.full_name),
        page_no,
        page_size,
        lambda u: UserView.model_validate(u).model_dump(mode="json"),
    )


@app.patch("/api/users/{id}", response_model=UserView)
def update_user(
    id: UUID, data: UserUpdate, user=Depends(require("users")), db=Depends(get_db)
):
    target = get(db, User, id, True)
    if target.id == user.id and (data.role != "director" or not data.is_active):
        fail("self_demotion", "You cannot disable or demote your own director account.")
    before = UserView.model_validate(target).model_dump(mode="json")
    for key, value in data.model_dump().items():
        setattr(target, key, value)
    audit(
        db,
        user,
        "user.permissions_changed",
        target,
        "Role and optional grants updated",
        before,
        data.model_dump(),
    )
    db.commit()
    return target


CATALOGS = {
    "categories": Category,
    "qualifications": Qualification,
    "committees": Committee,
}


@app.get("/api/catalogs/{kind}", response_model=Page)
def catalogs(
    kind: str,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(100, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if kind not in CATALOGS:
        fail("not_found", "Unknown catalog.", 404)
    cls = CATALOGS[kind]
    return page(db, select(cls).order_by(cls.name), page_no, page_size)


@app.post("/api/catalogs/{kind}", response_model=ObjectView)
def catalog_create(
    kind: str, data: CatalogIn, user=Depends(require("catalogs")), db=Depends(get_db)
):
    if kind not in CATALOGS:
        fail("not_found", "Unknown catalog.", 404)
    item = CATALOGS[kind](**data.model_dump())
    db.add(item)
    audit(db, user, "catalog.created", item, f"Created {item.name}")
    db.commit()
    return serialize(item)


@app.patch("/api/catalogs/{kind}/{id}", response_model=ObjectView)
def catalog_update(
    kind: str,
    id: UUID,
    data: CatalogIn,
    user=Depends(require("catalogs")),
    db=Depends(get_db),
):
    if kind not in CATALOGS:
        fail("not_found", "Unknown catalog.", 404)
    item = get(db, CATALOGS[kind], id)
    before = serialize(item)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    audit(
        db,
        user,
        "catalog.updated",
        item,
        f"Updated {item.name}",
        before,
        serialize(item),
    )
    db.commit()
    return serialize(item)


@app.get("/api/judges", response_model=Page)
def judges(
    request: Request,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot read judge contacts.", 403)
    stmt = judge_query(dict(request.query_params))
    result = page(db, stmt, page_no, page_size, lambda j: j)
    result["items"] = judge_views(db, result["items"])
    return result


@app.post("/api/judges", response_model=ObjectView)
def judge_create(data: JudgeIn, user=Depends(require("judges")), db=Depends(get_db)):
    judge = write_judge(db, data.model_dump(), user)
    db.commit()
    return judge_views(db, [judge])[0]


@app.post("/api/judges/bulk")
def judge_bulk(data: Bulk, user=Depends(require("judges")), db=Depends(get_db)):
    if not data.confirmed:
        fail("confirmation_required", "Confirm the bulk changes.")
    judges = db.scalars(
        select(Judge)
        .where(Judge.id.in_(data.ids), Judge.merged_into_id.is_(None))
        .with_for_update()
    ).all()
    for judge in judges:
        before = serialize(judge)
        if data.status:
            judge.status = data.status
        add_relations(
            db,
            judge,
            {
                "categories": [data.category] if data.category else [],
                "qualifications": [data.qualification] if data.qualification else [],
            },
        )
        audit(
            db,
            user,
            "judge.updated",
            judge,
            "Bulk contact update",
            before,
            serialize(judge),
        )
    db.commit()
    return {"updated": len(judges)}


@app.post("/api/judges/export")
def judge_export(data: Bulk, user=Depends(current_user), db=Depends(get_db)):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot export judges.", 403)
    records = judge_views(
        db, db.scalars(select(Judge).where(Judge.id.in_(data.ids))).all()
    )
    return Response(
        csv_output(records, FIELDS),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=judges.csv"},
    )


@app.get("/api/judges/{id}", response_model=ObjectView)
def judge_detail(id: UUID, user=Depends(current_user), db=Depends(get_db)):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot read judge contacts.", 403)
    return judge_views(db, [get(db, Judge, id)])[0]


@app.patch("/api/judges/{id}", response_model=ObjectView)
def judge_update(
    id: UUID, data: JudgeIn, user=Depends(require("judges")), db=Depends(get_db)
):
    judge = write_judge(db, data.model_dump(), user, get(db, Judge, id, True))
    db.commit()
    return judge_views(db, [judge])[0]


@app.post("/api/judges/{id}/merge", response_model=ObjectView)
def merge_contacts(
    id: UUID, data: MergeContacts, user=Depends(require("imports")), db=Depends(get_db)
):
    if not data.confirmed or id == data.merged_judge_id:
        fail("invalid_merge", "Confirm a merge of two different contacts.")
    # Consistent order prevents competing merges from deadlocking.
    locked = {
        j.id: j
        for j in db.scalars(
            select(Judge)
            .where(Judge.id.in_([id, data.merged_judge_id]))
            .order_by(Judge.id)
            .with_for_update()
        )
    }
    if len(locked) != 2 or any(j.merged_into_id for j in locked.values()):
        fail("invalid_merge", "Both contacts must be active records.")
    survivor, other = locked[id], locked[data.merged_judge_id]
    merge_data(
        db,
        survivor,
        judge_views(db, [other])[0],
        data.field_decisions,
        user,
        other=other,
    )
    db.commit()
    return judge_views(db, [survivor])[0]


@app.get("/api/judges/{id}/history", response_model=Page)
def judge_history(
    id: UUID,
    kind: str = "engagements",
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    if not (allowed(user, "judges") or allowed(user, "imports")):
        fail("forbidden", "Cannot view history.", 403)
    linked_ids = select(Judge.id).where(or_(Judge.id == id, Judge.merged_into_id == id))
    if kind == "messages":
        stmt = (
            select(Outbound)
            .join(Recipient)
            .where(Recipient.judge_id.in_(linked_ids))
            .order_by(Outbound.created_at.desc())
        )
    elif kind == "merges":
        stmt = (
            select(MergeEvent)
            .where(MergeEvent.survivor_judge_id == id)
            .order_by(MergeEvent.created_at.desc())
        )
    elif kind == "imports":
        stmt = (
            select(ImportRow)
            .where(ImportRow.matched_judge_id.in_(linked_ids))
            .order_by(ImportRow.created_at.desc())
        )
    else:
        stmt = (
            select(Engagement)
            .where(Engagement.judge_id.in_(linked_ids))
            .order_by(Engagement.event_year.desc())
        )
    return page(db, stmt, page_no, page_size)


@app.get("/api/judges/{id}/audit", response_model=Page)
def judge_audit(
    id: UUID,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(require("judges")),
    db=Depends(get_db),
):
    return page(
        db,
        select(Audit)
        .where(Audit.entity_id == str(id), Audit.entity_type == "judge_contacts")
        .order_by(Audit.created_at.desc()),
        page_no,
        page_size,
    )


@app.get("/api/audit-events", response_model=Page)
def audit_events(
    q: str = "",
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user=Depends(require("audit")),
    db=Depends(get_db),
):
    stmt = select(Audit).order_by(Audit.created_at.desc())
    if q:
        stmt = stmt.where(
            or_(Audit.action.ilike(f"%{q}%"), Audit.summary.ilike(f"%{q}%"))
        )
    result = page(db, stmt, page_no, page_size)
    if (
        user.role == "technology_administrator"
        and "private_tickets" not in user.permissions
    ):
        for item in result["items"]:
            if item["entity_type"] in {
                "tickets",
                "ticket_internal_notes",
                "ticket_messages",
            }:
                item["before_data"] = item["after_data"] = None
                item["summary"] = "Ticket action (content restricted)"
    return result


from .imports import router as imports_router
from .campaigns import router as campaigns_router
from .tickets import router as tickets_router
from .dashboard import router as dashboard_router
from .pilots import router as pilots_router
from .directory import router as directory_router
from .inbox import router as inbox_router

app.include_router(imports_router)
app.include_router(campaigns_router)
app.include_router(tickets_router)
app.include_router(dashboard_router)
app.include_router(pilots_router)
app.include_router(directory_router)
app.include_router(inbox_router)


@app.get("/api/system")
def system_configuration(user=Depends(require("jobs")), db=Depends(get_db)):
    import os
    import urllib.request

    worker_status = "unavailable"
    try:
        with urllib.request.urlopen("http://worker:8001/health", timeout=2) as response:
            worker_status = "healthy" if response.status == 200 else "unhealthy"
    except Exception:
        pass
    db.execute(text("SELECT 1"))
    return {
        "api": "healthy",
        "database": "healthy",
        "worker": worker_status,
        "email_provider": "mock",
        "sandbox_enforced": True,
        "max_import_bytes": int(os.getenv("IMPORT_MAX_BYTES", "2097152")),
        "max_import_rows": int(os.getenv("IMPORT_MAX_ROWS", "5000")),
        "retry_limit": 3,
        "stale_claim_minutes": 5,
        "configuration_source": "Environment variables; restart services after changing .env",
        "queue": dict(
            db.execute(
                select(Outbound.status, func.count()).group_by(Outbound.status)
            ).all()
        ),
    }
