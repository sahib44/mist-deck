import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from mist.db import engine, SessionLocal, Base
from mist.main import app
from mist.seed import seed


@pytest.fixture(autouse=True)
def database():
    assert engine.url.database.endswith(
        "_test"
    ), "Tests require an isolated _test database"
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                + ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
                + " RESTART IDENTITY CASCADE"
            )
        )
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        client.headers["X-MIST-Request"] = "1"
        yield client


@pytest.fixture
def director(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "director@example.com", "password": os.environ["SEED_PASSWORD"]},
    )
    assert response.status_code == 200, response.text
    return client
