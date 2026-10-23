import csv
import os
from pathlib import Path
from sqlalchemy import select
from .db import SessionLocal
from .models import User, Committee, Category, Qualification
from .auth import hasher
from .services import normalize_row, write_judge


def seed(db):
    if db.scalar(select(User).limit(1)):
        return
    password = os.environ["SEED_PASSWORD"]
    for short, role, name in [
        ("director", "director", "Demo Director"),
        ("tech", "technology_administrator", "Demo Technology"),
        ("competitions", "competitions_administrator", "Demo Competitions"),
        ("support", "support_staff", "Demo Support"),
    ]:
        db.add(
            User(
                full_name=name,
                email=f"{short}@example.com",
                password_hash=hasher.hash(password),
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


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
