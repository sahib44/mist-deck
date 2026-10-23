import hashlib
import os
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db, now
from .models import User, Session

hasher = PasswordHasher()
ROLE_PERMISSIONS = {
    "director": {
        "judges",
        "imports",
        "campaigns",
        "approve",
        "tickets",
        "catalogs",
        "audit",
        "users",
        "outbox",
        "jobs",
    },
    "technology_administrator": {"imports", "catalogs", "audit", "outbox", "jobs"},
    "competitions_administrator": {
        "judges",
        "imports",
        "campaigns",
        "tickets",
        "catalogs",
        "outbox",
    },
    "support_staff": {"tickets"},
}


def allowed(user, permission):
    return permission in ROLE_PERMISSIONS.get(user.role, set()) or (
        permission == "approve" and "campaign_approver" in user.permissions
    )


def fail(code, message, status=400):
    raise HTTPException(status, detail={"code": code, "message": message})


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("mist_session", "")
    session = db.scalar(
        select(Session).where(
            Session.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            Session.expires_at > now(),
        )
    )
    user = db.get(User, session.user_id) if session else None
    if not user or not user.is_active:
        fail("unauthenticated", "Please sign in.", 401)
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.headers.get("X-MIST-Request") != "1"
    ):
        fail("csrf", "Missing request protection header.", 403)
    return user


def require(permission):
    def dependency(user=Depends(current_user)):
        if not allowed(user, permission):
            fail("forbidden", "Your role does not allow this action.", 403)
        return user

    return dependency


def login(db, email, password, response):
    user = db.scalar(
        select(User).where(
            User.email == email.strip().lower(), User.is_active.is_(True)
        )
    )
    try:
        hasher.verify(
            user.password_hash if user else hasher.hash("unmatchable"), password
        )
    except VerificationError:
        fail("invalid_credentials", "Email or password is incorrect.", 401)
    if not user:
        fail("invalid_credentials", "Email or password is incorrect.", 401)
    token = secrets.token_urlsafe(48)
    db.add(
        Session(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now() + timedelta(hours=12),
        )
    )
    user.last_login_at = now()
    db.commit()
    response.set_cookie(
        "mist_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE") == "true",
        max_age=43200,
    )
    return user
