from mist.auth import hasher
from mist.models import User
from mist.db import SessionLocal
from sqlalchemy import select


def test_health_login_and_password_security(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/judges").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "director@example.com", "password": "wrong"},
        ).status_code
        == 401
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == "director"))
        assert user.password_hash.startswith("$argon2id$")


def test_judges_and_roles(director):
    result = director.get("/api/judges").json()
    assert result["total"] == 24
    assert "password_hash" not in director.get("/api/users").text
    assert director.get("/api/judges?qualification=Arts").json()["total"] == 6
    assert director.get("/api/dashboard").status_code == 200


def test_support_cannot_read_judges(client):
    import os

    client.post(
        "/api/auth/login",
        json={"email": "support@example.com", "password": os.environ["SEED_PASSWORD"]},
    )
    assert client.get("/api/judges").status_code == 403
    assert client.get("/api/imports").status_code == 403
    assert client.get("/api/tickets").json()["total"] == 0
