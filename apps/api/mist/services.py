import csv
import io
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from uuid import UUID
import bleach
from sqlalchemy import select, func, or_, delete
from .models import *
from .auth import fail

FIELDS = [
    "first_name",
    "last_name",
    "display_name",
    "primary_email",
    "alternate_email",
    "organization",
    "job_title",
    "phone",
    "status",
    "do_not_contact",
    "notes",
    "qualifications",
    "categories",
    "years",
]
TEMPLATE_VARS = {
    "judge_name",
    "first_name",
    "category_name",
    "organization",
    "event_name",
    "event_date",
    "response_deadline",
}


def clean(value):
    return bleach.clean(str(value or ""), tags=[], attributes={}, strip=True)


def email(value):
    return str(value or "").strip().lower()


def safe_email(value, optional=False):
    value = email(value)
    if not value and optional:
        return ""
    local = value.partition("@")[0]
    if (
        not re.fullmatch(
            r"[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@example\.(com|org|net)", value
        )
        or len(value) > 254
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        fail(
            "sandbox_email_required",
            "Use a valid address at example.com, example.org, or example.net.",
        )
    return value


def normalized(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(
        "".join(
            c if not unicodedata.category(c).startswith("P") else " " for c in value
        ).split()
    )


def serialize(obj):
    data = {}
    for column in obj.__table__.columns:
        if column.name in {"password_hash", "token_hash"}:
            continue
        v = getattr(obj, column.name)
        data[column.name] = (
            str(v)
            if isinstance(v, UUID)
            else v.isoformat() if isinstance(v, datetime) else v
        )
    return data


def audit(db, actor, action, obj, summary, before=None, after=None):
    db.flush()
    db.add(
        Audit(
            actor_user_id=actor.id if actor else None,
            action=action,
            entity_type=obj.__tablename__,
            entity_id=str(obj.id),
            summary=summary,
            before_data=before,
            after_data=after,
        )
    )


def get(db, cls, id, lock=False):
    stmt = select(cls).where(cls.id == id)
    if lock:
        stmt = stmt.with_for_update()
    result = db.scalar(stmt)
    if not result:
        fail("not_found", "Record not found.", 404)
    return result


def page(db, stmt, page=1, page_size=25, transform=serialize):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    records = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [transform(x) for x in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def split_values(value):
    return [v.strip() for v in re.split(r"[;|]", str(value or "")) if v.strip()]


def judge_views(db, judges):
    ids = [j.id for j in judges]
    quals, cats, years = {}, {}, {}
    for jid, name in db.execute(
        select(JudgeQualification.judge_id, Qualification.name)
        .join(Qualification)
        .where(JudgeQualification.judge_id.in_(ids))
    ):
        quals.setdefault(jid, []).append(name)
    for jid, name in db.execute(
        select(JudgeCategory.judge_id, Category.name)
        .join(Category)
        .where(JudgeCategory.judge_id.in_(ids))
    ):
        cats.setdefault(jid, []).append(name)
    for jid, year in db.execute(
        select(Engagement.judge_id, Engagement.event_year).where(
            Engagement.judge_id.in_(ids)
        )
    ):
        years.setdefault(jid, []).append(year)
    return [
        {
            **serialize(j),
            "qualifications": sorted(quals.get(j.id, [])),
            "categories": sorted(cats.get(j.id, [])),
            "years": sorted(set(years.get(j.id, []))),
        }
        for j in judges
    ]


def catalog_id(db, cls, name):
    name = clean(name).strip()[:200]
    item = db.scalar(select(cls).where(func.lower(cls.name) == name.lower()))
    if not item:
        item = cls(name=name)
        db.add(item)
        db.flush()
    return item.id


def add_relations(db, judge, data):
    for key, cls, link, column in [
        ("qualifications", Qualification, JudgeQualification, "qualification_id"),
        ("categories", Category, JudgeCategory, "category_id"),
    ]:
        for name in data.get(key, []):
            cid = catalog_id(db, cls, name)
            if not db.get(link, (judge.id, cid)):
                db.add(link(judge_id=judge.id, **{column: cid}))
    for year in data.get("years", []):
        year = int(year)
        if year < 1900 or year > 2200:
            fail("invalid_year", "Historical years must be between 1900 and 2200.")
        if not db.scalar(
            select(Engagement).where(
                Engagement.judge_id == judge.id, Engagement.event_year == year
            )
        ):
            db.add(Engagement(judge_id=judge.id, event_year=year, outcome="served"))


def write_judge(db, data, actor, existing=None, source="manual"):
    db.execute(select(func.pg_advisory_xact_lock(410261)))
    judge = existing or Judge(created_by=actor.id, source=source)
    before = serialize(judge) if existing else None
    for key in FIELDS:
        if key in {"qualifications", "categories", "years"} or key not in data:
            continue
        value = data[key]
        if key.endswith("email"):
            value = safe_email(value, optional=True)
        elif isinstance(value, str):
            value = clean(value)
        setattr(judge, key, value)
    judge.updated_by = actor.id
    db.add(judge)
    db.flush()
    add_relations(db, judge, data)
    audit(
        db,
        actor,
        "judge.updated" if existing else "judge.created",
        judge,
        f"Contact {judge.display_name}",
        before,
        serialize(judge),
    )
    if before and before["do_not_contact"] != judge.do_not_contact:
        audit(
            db,
            actor,
            "judge.do_not_contact",
            judge,
            "Contact preference changed",
            {"do_not_contact": before["do_not_contact"]},
            {"do_not_contact": judge.do_not_contact},
        )
    return judge


def judge_query(filters):
    stmt = select(Judge).where(Judge.merged_into_id.is_(None))
    if q := filters.get("q"):
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                *[
                    getattr(Judge, field).ilike(pattern)
                    for field in [
                        "display_name",
                        "primary_email",
                        "organization",
                        "job_title",
                    ]
                ],
                Judge.id.in_(
                    select(JudgeQualification.judge_id)
                    .join(Qualification)
                    .where(Qualification.name.ilike(pattern))
                ),
                Judge.id.in_(
                    select(JudgeCategory.judge_id)
                    .join(Category)
                    .where(Category.name.ilike(pattern))
                ),
            )
        )
    if filters.get("status"):
        stmt = stmt.where(Judge.status == filters["status"])
    for key, link, cls, column in [
        ("qualification", JudgeQualification, Qualification, "qualification_id"),
        ("category", JudgeCategory, Category, "category_id"),
    ]:
        if filters.get(key):
            stmt = stmt.where(
                Judge.id.in_(
                    select(link.judge_id)
                    .join(cls, cls.id == getattr(link, column))
                    .where(cls.name == filters[key])
                )
            )
    if filters.get("year") or filters.get("outcome"):
        sub = select(Engagement.judge_id)
        if filters.get("year"):
            try:
                sub = sub.where(Engagement.event_year == int(filters["year"]))
            except ValueError:
                fail("invalid_year", "Year must be a number.")
        if filters.get("outcome"):
            sub = sub.where(Engagement.outcome == filters["outcome"])
        stmt = stmt.where(Judge.id.in_(sub))
    if filters.get("do_not_contact") in {"true", "false"}:
        stmt = stmt.where(Judge.do_not_contact == (filters["do_not_contact"] == "true"))
    if filters.get("not_contacted_year"):
        try:
            year = int(filters["not_contacted_year"])
        except ValueError:
            fail("invalid_year", "Year must be a number.")
        stmt = stmt.where(
            or_(
                Judge.last_contacted_at.is_(None),
                func.extract("year", Judge.last_contacted_at) < year,
            )
        )
    sort = filters.get("sort", "name")
    if sort == "years":
        stmt = stmt.order_by(
            select(func.count(Engagement.id))
            .where(Engagement.judge_id == Judge.id)
            .scalar_subquery()
            .desc()
        )
    else:
        stmt = stmt.order_by(
            {
                "name": Judge.display_name,
                "organization": Judge.organization,
                "last_contacted": Judge.last_contacted_at.desc().nullslast(),
            }.get(sort, Judge.display_name)
        )
    return stmt.order_by(Judge.id)


def duplicate_match(incoming, existing):
    a = {email(incoming.get(k)) for k in ["primary_email", "alternate_email"]} - {""}
    b = {email(existing.get(k)) for k in ["primary_email", "alternate_email"]} - {""}
    b.update(existing.get("preserved_emails", []))
    if incoming.get("primary_email") and email(incoming["primary_email"]) == email(
        existing.get("primary_email")
    ):
        return "exact_email", 1.0, "Exact email match after trimming and lowercasing"
    if a & b:
        return (
            "alternate_email",
            0.98,
            "Primary or alternate email matches an existing address",
        )
    name_a, name_b = normalized(incoming.get("display_name")), normalized(
        existing.get("display_name")
    )
    org_a, org_b = normalized(incoming.get("organization")), normalized(
        existing.get("organization")
    )
    same_org = bool(org_a and org_a == org_b)
    if name_a and name_a == name_b and same_org:
        return "name_organization", 0.85, "Same normalized name and organization"
    if name_a and name_b and SequenceMatcher(None, name_a, name_b).ratio() >= 0.82:
        if same_org:
            return (
                "similar_organization",
                0.72,
                "Possible spelling variation in name with matching organization",
            )
        return (
            "name_only",
            0.35,
            "Similar name only; insufficient evidence to merge automatically",
        )
    return None


def normalize_row(raw, mapping):
    data = {
        field: " ".join(str(raw.get(header, "") or "").split())
        for field, header in mapping.items()
        if header
    }
    if not data.get("display_name"):
        data["display_name"] = " ".join(
            [data.get("first_name", ""), data.get("last_name", "")]
        ).strip()
    if not data.get("first_name") and data["display_name"]:
        parts = data["display_name"].split(" ", 1)
        data["first_name"], data["last_name"] = parts[0], (
            parts[1] if len(parts) > 1 else ""
        )
    data["primary_email"] = email(data.get("primary_email"))
    data["alternate_email"] = email(data.get("alternate_email"))
    data["qualifications"] = split_values(data.get("qualifications"))
    data["categories"] = split_values(data.get("categories"))
    errors = []
    try:
        data["years"] = [int(x) for x in split_values(data.get("years"))]
        if any(y < 1900 or y > 2200 for y in data["years"]):
            errors.append("Historical years must be between 1900 and 2200")
    except ValueError:
        data["years"] = []
        errors.append("Years judged must be semicolon-separated numbers")
    for field in ["primary_email", "alternate_email"]:
        try:
            safe_email(data[field], optional=True)
        except Exception:
            errors.append(
                f"{field}: only valid example.com, example.org, example.net addresses are allowed"
            )
    if not data["display_name"] and not data["primary_email"]:
        errors.append("Missing all usable identity fields")
    if not data["display_name"]:
        data["display_name"] = data["primary_email"]
    data["status"] = data.get("status") or "prospective"
    if data["status"] not in {
        "prospective",
        "contacted",
        "interested",
        "confirmed",
        "declined",
        "inactive",
    }:
        errors.append("Invalid judge status")
    data["do_not_contact"] = str(data.get("do_not_contact", "")).lower() in {
        "true",
        "yes",
        "1",
    }
    limits = {
        "first_name": 200,
        "last_name": 200,
        "display_name": 400,
        "organization": 300,
        "job_title": 200,
        "phone": 50,
        "notes": 20000,
    }
    for field, limit in limits.items():
        if len(data.get(field, "")) > limit:
            errors.append(f"{field} exceeds {limit} characters")
    return data, errors


def merge_data(db, survivor, incoming, decisions, actor, row=None, other=None):
    before = judge_views(db, [survivor])[0]
    for field in decisions:
        if field not in FIELDS or field in {
            "years",
            "qualifications",
            "categories",
            "notes",
        }:
            fail("invalid_merge_field", f"Cannot select a scalar value for {field}.")
    emails = set(
        before.get("preserved_emails", []) + incoming.get("preserved_emails", [])
    )
    for source in [before, incoming]:
        emails.update(
            email(source.get(k))
            for k in ["primary_email", "alternate_email"]
            if source.get(k)
        )
    for field in FIELDS:
        if field in {
            "qualifications",
            "categories",
            "years",
            "notes",
            "do_not_contact",
        }:
            continue
        if decisions.get(field) == "incoming" or (
            not getattr(survivor, field, "") and decisions.get(field) != "existing"
        ):
            if field in incoming:
                setattr(survivor, field, incoming[field])
    survivor.do_not_contact = bool(
        survivor.do_not_contact or incoming.get("do_not_contact")
    )
    survivor.preserved_emails = sorted(
        emails - {survivor.primary_email, survivor.alternate_email}
    )
    notes = [n for n in [survivor.notes, incoming.get("notes", "")] if n]
    survivor.notes = "\n\n".join(dict.fromkeys(notes))
    survivor.source = "\n".join(
        dict.fromkeys(
            [
                survivor.source,
                f"import row {row.id}" if row else f"merged contact {other.id}",
            ]
        )
    )
    add_relations(db, survivor, incoming)
    if other:
        # Historical campaign recipients remain attached to the retained tombstone, preserving immutable previews.
        for engagement in db.scalars(
            select(Engagement).where(Engagement.judge_id == other.id)
        ):
            engagement.judge_id = survivor.id
        for child in db.scalars(select(Judge).where(Judge.merged_into_id == other.id)):
            child.merged_into_id = survivor.id
        for link, column in [
            (JudgeQualification, "qualification_id"),
            (JudgeCategory, "category_id"),
        ]:
            for relation in db.scalars(select(link).where(link.judge_id == other.id)):
                target = db.get(link, (survivor.id, getattr(relation, column)))
                if target:
                    target.notes = "\n".join(
                        dict.fromkeys(filter(None, [target.notes, relation.notes]))
                    )
        other.merged_into_id = survivor.id
        other.do_not_contact = True
    survivor.updated_by = actor.id
    db.flush()
    after = judge_views(db, [survivor])[0]
    event = MergeEvent(
        survivor_judge_id=survivor.id,
        merged_judge_id=other.id if other else None,
        import_row_id=row.id if row else None,
        before_snapshot={"existing": before, "incoming": incoming},
        after_snapshot=after,
        field_decisions=decisions,
        merged_by=actor.id,
    )
    db.add(event)
    audit(
        db,
        actor,
        "contact.merged",
        survivor,
        "Merged contact; original values retained in merge snapshot",
        event.before_snapshot,
        after,
    )
    if before["do_not_contact"] != survivor.do_not_contact:
        audit(
            db,
            actor,
            "judge.do_not_contact",
            survivor,
            "Merge preserved do-not-contact suppression",
        )
    return survivor


def render_template(template, values):
    variables = re.findall(r"{{\s*([^{}]+?)\s*}}", template)
    unknown = set(variables) - TEMPLATE_VARS
    if unknown:
        fail(
            "unknown_template_variable",
            "Unknown template variables: " + ", ".join(sorted(unknown)),
        )
    rendered = re.sub(
        r"{{\s*([^{}]+?)\s*}}", lambda m: str(values.get(m.group(1), "")), template
    )
    if "{{" in rendered or "}}" in rendered:
        fail("invalid_template", "Template braces must enclose a supported variable.")
    return clean(rendered)


def csv_output(records, fields):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        safe = {}
        for key in fields:
            value = record.get(key, "")
            if isinstance(value, list):
                value = ";".join(map(str, value))
            if isinstance(value, str) and value.startswith(
                ("=", "+", "-", "@", "\t", "\r")
            ):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return out.getvalue()
