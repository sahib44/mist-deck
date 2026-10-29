import csv
import os
from pathlib import Path
from sqlalchemy import select, delete
from .db import SessionLocal
from .models import User, Session, Committee, Category, Qualification, PilotCompetition
from .competition_catalog import CATEGORIES
from .auth import hasher
from .services import normalize_row, write_judge


def seed(db):
    if db.scalar(select(User).limit(1)):
        seed_competition_accounts(db)
        seed_competitions(db)
        return
    password = os.environ["SEED_PASSWORD"]
    for short, role, name in [
        ("director", "director", "Demo Director"),
        ("tech", "technology_administrator", "Demo Technology"),
        ("competitions", "competitions_member", "Competition Heads"),
        ("chair", "competitions_chair", "Competitions Chair"),
        ("support", "support_staff", "Demo Support"),
    ]:
        db.add(
            User(
                full_name=name,
                email=f"{short}@example.com",
                password_hash=hasher.hash(account_password(role)),
                role=role,
                permissions=["campaign_approver"] if short == "competitions" else [],
            )
        )
    db.flush()
    director = db.scalar(select(User).where(User.role == "director"))
    for cls, names in [
        (Committee, ["Competitions", "Registration", "General Support"]),
        (Category, ["Visual Arts", "Creative Writing", "Debate", "Science"]),
        (Qualification, ["Arts", "Writing", "Public Speaking", "Science"]),
    ]:
        for name in names:
            db.add(cls(name=name, description="Fabricated development catalog"))
    db.flush()
    path = Path("/sample-data/mock_judges.csv")
    if not path.exists():
        path = Path("../../sample-data/mock_judges.csv")
    if path.exists():
        for raw in csv.DictReader(path.open()):
            data, errors = normalize_row(raw, {k: k for k in raw})
            if not errors:
                write_judge(db, data, director, source="fabricated development seed")
    db.commit()
    seed_competition_accounts(db)
    seed_competitions(db)


def account_password(role):
    key = {"competitions_chair": "COMPETITIONS_CHAIR_PASSWORD", "competitions_member": "COMPETITIONS_MEMBER_PASSWORD"}.get(role, "SEED_PASSWORD")
    return os.getenv(key) or os.environ["SEED_PASSWORD"]


def seed_competition_accounts(db, rotate_passwords=False):
    password = os.environ["SEED_PASSWORD"]
    for email, role, name in [("chair@example.com", "competitions_chair", "Competitions Chair"), ("competitions@example.com", "competitions_member", "Competition Heads")]:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            if rotate_passwords:
                user.password_hash = hasher.hash(account_password(role))
                db.execute(delete(Session).where(Session.user_id == user.id))
            if user.role == "competitions_administrator":
                user.role = role
                user.full_name = name
        else:
            db.add(User(email=email, role=role, full_name=name, password_hash=hasher.hash(account_password(role)), permissions=[]))
    db.commit()


def seed_competitions(db):
    director = db.scalar(select(User).where(User.role == "director"))
    if not director:
        return
    for slug, (_, names) in CATEGORIES.items():
        for name in names:
            if not db.scalar(select(PilotCompetition.id).where(
                PilotCompetition.category_slug == slug,
                PilotCompetition.name == name,
                PilotCompetition.event_year == 2027,
                PilotCompetition.is_pilot.is_(False),
            )):
                db.add(PilotCompetition(
                    name=name, event_year=2027, category_slug=slug,
                    is_pilot=False, created_by=director.id,
                ))
    if not db.scalar(select(PilotCompetition.id).where(
        PilotCompetition.category_slug == "arts",
        PilotCompetition.name == "Culinary Arts",
        PilotCompetition.event_year == 2027,
    )):
        db.add(PilotCompetition(
            name="Culinary Arts", event_year=2027, category_slug="arts",
            is_pilot=True, created_by=director.id,
        ))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
