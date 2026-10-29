"""Explicit local reset: retain accounts, competitions and documents; clear activity."""
import os
import json
from sqlalchemy import text
from .db import engine, Base, SessionLocal
from . import models  # register tables
from .seed import seed_competition_accounts


def reset():
    if os.getenv("MIST_SANDBOX_RESET") != "1" or engine.url.database != "mist":
        raise RuntimeError("Reset requires MIST_SANDBOX_RESET=1 and the local mist database")
    keep = {"users", "sessions", "committees", "competition_categories", "qualification_tags", "pilot_competitions", "pilot_documents"}
    tables = [table.name for table in Base.metadata.sorted_tables if table.name not in keep]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join('"' + name + '"' for name in tables) + " RESTART IDENTITY"))
        connection.execute(text("ALTER SEQUENCE ticket_number_seq RESTART WITH 1"))
    with SessionLocal() as db:
        seed_competition_accounts(db, rotate_passwords=True)
    print(json.dumps({"reset": "local sandbox activity", "retained": sorted(keep)}))


if __name__ == "__main__":
    reset()
