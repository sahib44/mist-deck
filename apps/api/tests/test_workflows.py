import io
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4, UUID
import pytest
from sqlalchemy import select, func
from mist.db import SessionLocal, now
from mist.models import *
from mist.services import (
    email,
    normalized,
    duplicate_match,
    render_template,
    merge_data,
    judge_views,
    safe_email,
)
from mist.worker import claim, deliver, run_once


def login(client, role):
    r = client.post(
        "/api/auth/login",
        json={"email": f"{role}@example.com", "password": os.environ["SEED_PASSWORD"]},
    )
    assert r.status_code == 200, r.text


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def make_campaign(client, ids=None):
    judges = ok(client.get("/api/judges?page_size=100"))["items"]
    body = {
        "name": "Test invitations",
        "subject_template": "Hello {{first_name}}",
        "body_template": "Dear {{judge_name}}, {{organization}} / {{event_name}}",
        "judge_ids": ids if ids is not None else [j["id"] for j in judges[:3]],
        "variables": {"event_name": "Fabricated Event"},
    }
    return ok(client.post("/api/campaigns", json=body))


def queue(client, c):
    for action in ["submit", "approve", "queue"]:
        ok(client.post(f'/api/campaigns/{c["id"]}/{action}'))


def test_normalization_and_sandbox():
    assert email(" A.B+tag@EXAMPLE.COM ") == "a.b+tag@example.com"
    assert normalized("  STRAẞE   Studio, Inc. ") == normalized("strasse studio inc")
    for address in [
        "judge@invalid.test",
        "a@example.com.evil.test",
        "x@y@example.com",
        "x@example.com\nBcc:x@example.org",
    ]:
        with pytest.raises(Exception):
            safe_email(address)
    assert safe_email(" User@Example.org ") == "user@example.org"


@pytest.mark.parametrize(
    "incoming,existing,expected",
    [
        (
            {"primary_email": " A@EXAMPLE.COM "},
            {"primary_email": "a@example.com"},
            "exact_email",
        ),
        (
            {"primary_email": "a@example.com"},
            {"alternate_email": "a@example.com"},
            "alternate_email",
        ),
        (
            {"alternate_email": "a@example.com"},
            {"primary_email": "a@example.com"},
            "alternate_email",
        ),
        (
            {"display_name": "Zara Quill", "organization": "Studio, One"},
            {"display_name": "zara quill", "organization": "Studio One"},
            "name_organization",
        ),
        (
            {"display_name": "Zara Quil", "organization": "Studio One"},
            {"display_name": "Zara Quill", "organization": "Studio One"},
            "similar_organization",
        ),
        (
            {"display_name": "Zara Quill", "organization": "Different"},
            {"display_name": "Zara Quill", "organization": "Studio One"},
            "name_only",
        ),
    ],
)
def test_duplicate_match_levels(incoming, existing, expected):
    assert duplicate_match(incoming, existing)[0] == expected


def test_unknown_template_variables():
    with pytest.raises(Exception):
        render_template("Hello {{password}}", {})
    assert (
        render_template("<b>Hello {{first_name}}</b>", {"first_name": "Fable"})
        == "Hello Fable"
    )


def test_import_mapping_duplicates_commit_and_error_csv(director):
    data = Path("/sample-data/mock_judges_with_duplicates.csv").read_bytes()
    batch = ok(
        director.post("/api/imports", files={"file": ("judges.csv", data, "text/csv")})
    )
    assert (
        director.put(
            f'/api/imports/{batch["id"]}/mapping', json={"mapping": {"notes": "notes"}}
        ).status_code
        == 400
    )
    ok(
        director.put(
            f'/api/imports/{batch["id"]}/mapping', json={"mapping": batch["mapping"]}
        )
    )
    ok(director.post(f'/api/imports/{batch["id"]}/analyze'))
    analysis = ok(director.get(f'/api/imports/{batch["id"]}'))
    assert analysis["counts"]["invalid"] == 2
    assert analysis["counts"]["duplicate_review"] == 6
    assert (
        director.post(
            f'/api/imports/{batch["id"]}/commit', json={"confirmed": True}
        ).status_code
        == 400
    )
    matched_types = set()
    for _ in range(10):
        candidates = ok(
            director.get(f'/api/duplicates?batch_id={batch["id"]}&page_size=100')
        )["items"]
        strong = [x for x in candidates if x["confidence_score"] >= 0.7]
        if not strong:
            break
        candidate = strong[0]
        matched_types.add(candidate["match_type"])
        ok(
            director.post(
                f'/api/duplicates/{candidate["id"]}/resolve',
                json={
                    "decision": "merge",
                    "field_decisions": {
                        "organization": "incoming",
                        "job_title": "incoming",
                    },
                    "confirmed": True,
                },
            )
        )
    assert (
        "exact_email" in matched_types
        and "name_organization" in matched_types
        and "similar_organization" in matched_types
    )
    result = ok(
        director.post(f'/api/imports/{batch["id"]}/commit', json={"confirmed": True})
    )
    assert (
        result["created_count"],
        result["updated_count"],
        result["skipped_count"],
    ) == (2, 6, 2)
    assert (
        ok(
            director.post(
                f'/api/imports/{batch["id"]}/commit', json={"confirmed": True}
            )
        )["created_count"]
        == 2
    )
    assert ok(director.get("/api/judges"))["total"] == 26
    error = director.get(f'/api/imports/{batch["id"]}/errors')
    assert (
        "row_number" in error.text
        and "Missing all usable identity fields" in error.text
    )
    assert (
        "import.committed" in director.get("/api/audit-events?q=import.committed").text
    )


def test_csv_rejects_malformed_and_empty(director):
    for data in [
        b"",
        b"name,email\nOnly One",
        b"name,name\na,b",
        b'name,email\n"unclosed,a@example.com',
    ]:
        assert (
            director.post(
                "/api/imports", files={"file": ("bad.csv", data, "text/csv")}
            ).status_code
            == 400
        )


def test_merge_preserves_values_relationships_and_history(director):
    judges = ok(director.get("/api/judges"))["items"]
    a, b = judges[:2]
    c = make_campaign(director, [b["id"]])
    result = ok(
        director.post(
            f'/api/judges/{a["id"]}/merge',
            json={
                "merged_judge_id": b["id"],
                "field_decisions": {"organization": "incoming"},
                "confirmed": True,
            },
        )
    )
    assert b["primary_email"] in result["preserved_emails"]
    assert set(result["qualifications"]) >= set(
        a["qualifications"] + b["qualifications"]
    )
    assert ok(director.get(f'/api/campaigns/{c["id"]}/preview'))["total"] == 1
    history = ok(director.get(f'/api/judges/{a["id"]}/history?kind=merges'))
    assert (
        history["total"] == 1
        and history["items"][0]["before_snapshot"]["incoming"]["primary_email"]
        == b["primary_email"]
    )


def test_campaign_dnc_dedup_preview_idempotency(director):
    judges = ok(director.get("/api/judges?page_size=100"))["items"]
    blocked = next(j for j in judges if j["do_not_contact"])
    one = judges[0]
    c = make_campaign(director, [one["id"], one["id"], blocked["id"]])
    assert c["recipient_count"] == 1 and len(c["excluded"]) == 1
    assert (
        director.post(
            "/api/campaigns",
            json={
                "name": "Bad",
                "subject_template": "{{secret}}",
                "body_template": "Hello",
                "judge_ids": [one["id"]],
            },
        ).status_code
        == 400
    )
    queue(director, c)
    ok(director.post(f'/api/campaigns/{c["id"]}/queue'))
    while run_once():
        pass
    result = ok(director.get("/api/outbox"))
    assert result["total"] == 1 and result["items"][0]["status"] == "sent"
    assert result["items"][0]["attempt_count"] == 1
    assert ok(director.get(f'/api/campaigns/{c["id"]}'))["status"] == "completed"


def test_retry_bounds_stale_recovery_and_atomic_claim(director):
    c = make_campaign(director)
    queue(director, c)
    with SessionLocal() as db:
        jobs = db.scalars(select(Outbound)).all()
        for job in jobs:
            job.simulate_failure = True
        db.commit()
    for _ in range(3):
        while run_once():
            pass
        with SessionLocal() as db:
            for job in db.scalars(select(Outbound)):
                job.available_at = now() - timedelta(seconds=1)
            db.commit()
    with SessionLocal() as db:
        jobs = db.scalars(select(Outbound)).all()
        assert all(j.status == "failed" and j.attempt_count == 3 for j in jobs)
    assert not run_once()
    job = ok(director.get("/api/outbox"))["items"][0]
    ok(director.post(f'/api/outbox/{job["id"]}/failure', json={"enabled": False}))
    ok(director.post(f'/api/outbox/{job["id"]}/retry'))
    with SessionLocal() as a, SessionLocal() as b:
        claimed = claim(a, "stopped-worker")
        assert claimed
        assert claim(b, "second-worker") is None
        row = a.get(Outbound, claimed)
        row.claimed_at = now() - timedelta(minutes=6)
        a.commit()
        assert claim(b, "replacement-worker") == claimed
        deliver(a, claimed, "stopped-worker")
        deliver(b, claimed, "replacement-worker")
    with SessionLocal() as db:
        assert db.get(Outbound, claimed).status == "sent"


def test_cancellation_and_late_suppression_prevent_delivery(director):
    c = make_campaign(director)
    queue(director, c)
    with SessionLocal() as db:
        id = claim(db, "worker")
    ok(director.post(f'/api/campaigns/{c["id"]}/cancel'))
    with SessionLocal() as db:
        deliver(db, id, "worker")
    assert not run_once()
    assert all(
        m["status"] == "cancelled" for m in ok(director.get("/api/outbox"))["items"]
    )
    c2 = make_campaign(director)
    queue(director, c2)
    with SessionLocal() as db:
        for rec in db.scalars(
            select(Recipient).where(Recipient.campaign_id == UUID(c2["id"]))
        ):
            db.get(Judge, rec.judge_id).do_not_contact = True
        db.commit()
    while run_once():
        pass
    assert all(
        m["status"] == "cancelled" for m in ok(director.get("/api/outbox"))["items"]
    )


def test_ticket_note_reply_assignment_privacy_and_lifecycle(director):
    client = director
    ticket = ok(
        client.post(
            "/api/tickets",
            json={
                "requester_name": "Fictional Runner",
                "requester_email": "runner@example.org",
                "subject": "Fabricated question",
                "body": "<script>alert(1)</script>Can I revise my entry?",
            },
        )
    )
    id = ticket["id"]
    users = ok(client.get("/api/users"))["items"]
    support = next(u for u in users if u["role"] == "support_staff")
    ok(
        client.post(
            f"/api/tickets/{id}/assign", json={"assigned_user_id": support["id"]}
        )
    )
    login(client, "support")
    assert client.get(f"/api/tickets/{id}").status_code == 200
    ok(
        client.post(
            f"/api/tickets/{id}/notes",
            json={"body": "Private organizer context", "request_id": str(uuid4())},
        )
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Outbound)) == 0
    body = {"body": "A public answer", "request_id": str(uuid4())}
    ok(client.post(f"/api/tickets/{id}/messages", json=body))
    ok(client.post(f"/api/tickets/{id}/messages", json=body))
    assert ok(client.get(f"/api/tickets/{id}/messages"))["total"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Outbound)) == 1
    ok(client.post(f"/api/tickets/{id}/status", json={"status": "resolved"}))
    assert (
        client.post(
            f"/api/tickets/{id}/assign", json={"assigned_user_id": None}
        ).status_code
        == 403
    )
    login(client, "tech")
    assert client.get("/api/tickets").status_code == 403
    assert client.get(f"/api/tickets/{id}/notes").status_code == 403
    assert ok(client.get("/api/outbox"))["total"] == 0
    assert "Private organizer context" not in client.get("/api/audit-events").text
    login(client, "director")
    assert ok(client.get("/api/outbox"))["total"] == 1
    assert (
        "ticket.status_changed"
        in client.get("/api/audit-events?q=ticket.status_changed").text
    )


def test_competitions_ticket_scope_and_approval_grant(client):
    login(client, "director")
    ticket = ok(
        client.post(
            "/api/tickets",
            json={
                "requester_name": "Demo",
                "requester_email": "demo@example.com",
                "subject": "Private general support",
                "body": "Private",
            },
        )
    )
    users = ok(client.get("/api/users"))["items"]
    comp = next(u for u in users if u["role"] == "competitions_member")
    ok(
        client.patch(
            "/api/users/" + comp["id"],
            json={"role": comp["role"], "permissions": [], "is_active": True},
        )
    )
    login(client, "competitions")
    assert client.get("/api/tickets/" + ticket["id"]).status_code == 404
    assert ok(client.get("/api/tickets"))["total"] == 0
    c = make_campaign(client)
    ok(client.post(f'/api/campaigns/{c["id"]}/submit'))
    assert client.post(f'/api/campaigns/{c["id"]}/approve').status_code == 200
    assert client.get("/api/audit-events").status_code == 403


def test_saved_lists_are_removed(director):
    assert director.get("/api/saved-lists").status_code == 404
    assert director.post("/api/saved-lists", json={"name": "Retired"}).status_code == 404


def test_deduplicates_different_contacts_sharing_email(director):
    first = ok(director.get("/api/judges"))["items"][0]
    duplicate = ok(
        director.post(
            "/api/judges",
            json={
                "display_name": "Fictional Alternate Record",
                "primary_email": first["primary_email"].upper(),
            },
        )
    )
    campaign = make_campaign(director, [first["id"], duplicate["id"]])
    assert campaign["recipient_count"] == 1
    assert campaign["excluded"][0]["reason"] == "Duplicate normalized email"


def test_within_batch_exact_duplicate_and_merge(director):
    content = "Full Name,Email,Organization,Notes\nNovel Person,novelbatch@example.com,Demo,First note\nNovel Person,NOVELBATCH@example.com,Demo,Second note\n"
    b = ok(
        director.post(
            "/api/imports", files={"file": ("batch.csv", content, "text/csv")}
        )
    )
    ok(director.put(f'/api/imports/{b["id"]}/mapping', json={"mapping": b["mapping"]}))
    ok(director.post(f'/api/imports/{b["id"]}/analyze'))
    candidate = next(
        c
        for c in ok(director.get(f'/api/duplicates?batch_id={b["id"]}'))["items"]
        if c["match_type"] == "exact_email"
    )
    assert candidate["existing_row_id"]
    ok(
        director.post(
            f'/api/duplicates/{candidate["id"]}/resolve',
            json={"decision": "merge", "confirmed": True},
        )
    )
    result = ok(
        director.post(f'/api/imports/{b["id"]}/commit', json={"confirmed": True})
    )
    assert result["created_count"] == 1 and result["updated_count"] == 1
    judge = ok(director.get("/api/judges?q=novelbatch"))["items"][0]
    assert "First note" in judge["notes"] and "Second note" in judge["notes"]


def test_skip_locked_and_transactional_delivery_receipt(director):
    c = make_campaign(director)
    queue(director, c)
    with SessionLocal() as locked, SessionLocal() as other:
        first = locked.scalar(
            select(Outbound)
            .order_by(Outbound.available_at, Outbound.id)
            .with_for_update()
            .limit(1)
        )
        claimed = claim(other, "parallel-worker")
        assert claimed and claimed != first.id
        deliver(other, claimed, "parallel-worker")
        deliver(other, claimed, "parallel-worker")
        assert other.get(Outbound, claimed).attempt_count == 1


def test_csrf_and_export_formula_injection(director):
    from mist.services import csv_output

    director.headers.pop("X-MIST-Request")
    assert director.post("/api/auth/logout").status_code == 403
    assert "'=formula" in csv_output([{"value": "=formula"}], ["value"])


def test_private_ticket_grant_and_sandbox_validation(director):
    users = ok(director.get("/api/users"))["items"]
    tech = next(u for u in users if u["role"] == "technology_administrator")
    ticket = ok(
        director.post(
            "/api/tickets",
            json={
                "requester_name": "Private Demo",
                "requester_email": "private@example.com",
                "subject": "Private",
                "body": "Fabricated private context",
            },
        )
    )
    ok(
        director.patch(
            "/api/users/" + tech["id"],
            json={
                "role": tech["role"],
                "permissions": ["private_tickets"],
                "is_active": True,
            },
        )
    )
    login(director, "tech")
    assert director.get("/api/tickets/" + ticket["id"]).status_code == 200
    assert director.get("/api/users").status_code == 200
    for invalid in [
        ".person@example.com",
        "person.@example.org",
        "per..son@example.net",
    ]:
        with pytest.raises(Exception):
            safe_email(invalid)
