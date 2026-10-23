"""Reset only the dedicated, disposable end-to-end test database."""

import os
from sqlalchemy import text
from .db import engine, Base, SessionLocal
from .seed import seed

if __name__ == "__main__":
    if os.getenv("MIST_E2E_RESET") != "1" or engine.url.database != "mist_e2e":
        raise RuntimeError(
            "Reset is restricted to the dedicated mist_e2e database with MIST_E2E_RESET=1"
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                + ", ".join(
                    '"' + table.name + '"' for table in Base.metadata.sorted_tables
                )
                + " RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(text("ALTER SEQUENCE ticket_number_seq RESTART WITH 1"))
    with SessionLocal() as db:
        seed(db)
