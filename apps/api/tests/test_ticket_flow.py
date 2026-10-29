import os
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import select, func
from mist.db import SessionLocal, now
from mist.models import Ticket, TicketDraft, TicketNote, Notification, Outbound, User, TicketMessage
from mist.ticket_flow import close_idle_tickets
from mist.worker import run_once


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def login(client, name):
    return ok(client.post("/api/auth/login", json={"email": f"{name}@example.com", "password": os.environ["SEED_PASSWORD"]}))


def create(client):
    return ok(client.post("/api/tickets", json={"requester_name": "Sample Requester", "requester_email": "requester@example.org", "subject": "Rules question", "body": "Can you help with the rules?"}))


def request_review(client, ticket, kind="messages", body="Please send more details.", target="waiting_on_requester", resolution=""):
    detail = ok(client.get(f"/api/tickets/{ticket['id']}"))
    return ok(client.post(f"/api/tickets/{ticket['id']}/drafts", json={"kind": kind, "body": body, "target_status": target, "resolution_note": resolution, "expected_version": detail["version"], "request_id": str(uuid4())}))


def approve(client, ticket, review):
    original = ok(client.get("/api/auth/me"))["email"]
    login(client, "chair")
    result = ok(client.post(f"/api/tickets/{ticket['id']}/drafts/{review['id']}/approve"))
    ok(client.post("/api/auth/login", json={"email": original, "password": os.environ["SEED_PASSWORD"]}))
    return result


def test_new_ticket_alert_persists_until_status_changes_and_notes_are_newest_first(director):
    ticket = create(director)
    alert = ok(director.get("/api/notifications"))["items"][0]
    ok(director.post(f"/api/notifications/{alert['id']}/read"))
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    for number in range(28):
        ok(director.post(f"/api/tickets/{ticket['id']}/notes", json={"body": f"Finding {number:02d}", "request_id": str(uuid4())}))
    notes = ok(director.get(f"/api/tickets/{ticket['id']}/notes"))
    assert notes["items"][0]["body"] == "Finding 27"
    assert len(notes["items"]) == 25
    assert ok(director.get(f"/api/tickets/{ticket['id']}/notes?page=2"))["items"][0]["body"] == "Finding 02"
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    ok(director.post(f"/api/tickets/{ticket['id']}/status", json={"status": "in_progress"}))
    assert ok(director.get("/api/notifications"))["unread_count"] == 0


def test_status_requirements_are_atomic_and_keep_private_resolution_out_of_email(director):
    ticket = create(director)
    for status in ("waiting_on_requester", "waiting_on_organizer", "resolved"):
        assert director.post(f"/api/tickets/{ticket['id']}/status", json={"status": status}).status_code == 400
        assert ok(director.get(f"/api/tickets/{ticket['id']}"))["status"] == "new"
    assert ok(director.get(f"/api/tickets/{ticket['id']}/messages"))["total"] == 1
    assert ok(director.get(f"/api/tickets/{ticket['id']}/notes"))["total"] == 0
    assert ok(director.get("/api/outbox"))["total"] == 0
    waiting = ok(director.post(f"/api/tickets/{ticket['id']}/status", json={"status": "waiting_on_organizer", "internal_note": "Need to check the rulebook."}))
    assert waiting["status"] == "waiting_on_organizer" and waiting["auto_close_at"] is None
    result = ok(director.post(f"/api/tickets/{ticket['id']}/status", json={"status": "resolved", "resolution_note": "Privately confirmed with the rules chair.", "reply_body": "Your question is resolved."}))
    assert result["status"] == "resolved" and result["auto_close_at"]
    message = ok(director.get("/api/outbox"))["items"][0]
    assert message["body_text"] == "Your question is resolved."
    assert "Privately confirmed" not in message["body_text"]
    newest = ok(director.get(f"/api/tickets/{ticket['id']}/notes"))["items"][0]
    assert newest["kind"] == "resolution"
    assert newest["body"] == "Privately confirmed with the rules chair."


def test_chair_only_approval_notifies_requestor_and_does_not_send_until_head_confirms(director):
    login(director, "competitions")
    ticket = create(director)
    body = "Please send more details."
    assert director.post(f"/api/tickets/{ticket['id']}/messages", json={"body": body, "request_id": str(uuid4())}).status_code == 403
    review = request_review(director, ticket, body=body)
    assert not any(item["kind"] == "ticket_approval_requested" for item in ok(director.get("/api/notifications"))["items"])
    assert director.post(f"/api/tickets/{ticket['id']}/drafts/{review['id']}/approve").status_code == 403
    login(director, "chair")
    alerts = ok(director.get("/api/notifications"))["items"]
    assert any(item["kind"] == "ticket_approval_requested" and review["id"] in item["href"] for item in alerts)
    assert ok(director.get(f"/api/tickets/{ticket['id']}/drafts"))["items"][0]["body"] == body
    ok(director.post(f"/api/tickets/{ticket['id']}/drafts/{review['id']}/approve"))
    assert ok(director.get("/api/outbox"))["total"] == 0
    assert ok(director.get(f"/api/tickets/{ticket['id']}"))["status"] == "new"
    assert not any(item["kind"] == "ticket_draft_approved" for item in ok(director.get("/api/notifications"))["items"])
    login(director, "competitions")
    assert any(item["kind"] == "ticket_draft_approved" for item in ok(director.get("/api/notifications"))["items"])
    payload = {"status": "waiting_on_requester", "reply_body": body, "approval_id": review["id"], "request_id": str(uuid4()), "expected_version": ticket["version"]}
    result = ok(director.post(f"/api/tickets/{ticket['id']}/status", json=payload))
    assert result["status"] == "waiting_on_requester" and result["auto_close_at"] is None
    ok(director.post(f"/api/tickets/{ticket['id']}/status", json=payload))
    assert ok(director.get("/api/outbox"))["total"] == 1
    assert ok(director.get(f"/api/tickets/{ticket['id']}/messages"))["total"] == 2
    run_once("ticket-deadline-test")
    assert ok(director.get(f"/api/tickets/{ticket['id']}"))["auto_close_at"]


def test_approved_content_cannot_be_edited_or_used_after_new_ticket_activity(director):
    login(director, "competitions")
    ticket = create(director)
    review = request_review(director, ticket)
    approve(director, ticket, review)
    response = director.post(f"/api/tickets/{ticket['id']}/status", json={"status": "waiting_on_requester", "reply_body": "Changed after approval", "approval_id": review["id"]})
    assert response.status_code == 409
    assert ok(director.get("/api/outbox"))["total"] == 0
    ok(director.post(f"/api/tickets/{ticket['id']}/notes", json={"body": "New finding changes the context.", "request_id": str(uuid4())}))
    assert ok(director.get(f"/api/tickets/{ticket['id']}/drafts"))["items"][0]["status"] == "superseded"
    assert director.post(f"/api/tickets/{ticket['id']}/messages", json={"body": review["body"], "approval_id": review["id"], "request_id": str(uuid4())}).status_code == 403


def test_private_note_can_be_reviewed_and_saved_without_sending_any_email(director):
    login(director, "competitions")
    ticket = create(director)
    review = request_review(director, ticket, kind="notes", body="Checked the rulebook and need chair guidance.", target="waiting_on_organizer")
    approve(director, ticket, review)
    ok(director.post(f"/api/tickets/{ticket['id']}/status", json={"status": "waiting_on_organizer", "internal_note": review["body"], "approval_id": review["id"]}))
    assert ok(director.get("/api/outbox"))["total"] == 0
    assert ok(director.get(f"/api/tickets/{ticket['id']}/notes"))["items"][0]["body"] == review["body"]


def test_needs_reply_contains_new_in_progress_and_awaiting_organizer(director):
    expected = []
    for status in ("new", "in_progress", "waiting_on_organizer", "waiting_on_requester", "resolved"):
        ticket = create(director)
        if status != "new":
            payload = {"status": status}
            if status == "waiting_on_organizer": payload["internal_note"] = "Investigate rules."
            if status == "waiting_on_requester": payload["reply_body"] = "Please clarify."
            if status == "resolved": payload["resolution_note"] = "Resolved privately."
            ok(director.post(f"/api/tickets/{ticket['id']}/status", json=payload))
        if status in {"new", "in_progress", "waiting_on_organizer"}: expected.append(ticket["id"])
    assert {ticket["id"] for ticket in ok(director.get("/api/tickets?view=waiting"))["items"]} == set(expected)
    assert director.post(f"/api/tickets/{expected[0]}/status", json={"status": "responded"}).status_code == 422


def test_auto_close_only_waiting_requester_and_resolved_and_incoming_reopens(director):
    tickets = {status: create(director) for status in ("new", "in_progress", "waiting_on_organizer", "waiting_on_requester", "resolved")}
    with SessionLocal() as db:
        for status, item in tickets.items():
            row = db.get(Ticket, UUID(item["id"]))
            row.status, row.auto_close_at = status, now() - timedelta(seconds=1)
        db.commit()
        assert close_idle_tickets(db) == 2
    for status, item in tickets.items():
        assert ok(director.get(f"/api/tickets/{item['id']}"))["status"] == ("closed" if status in {"waiting_on_requester", "resolved"} else status)
    closed = tickets["waiting_on_requester"]
    received = ok(director.post("/api/inbox/simulate", json={"sender_email": "requester@example.org", "subject": f"Re: {closed['public_number']}", "body": "Here are the missing details.", "request_id": str(uuid4())}))
    assert received["ticket_id"] == closed["id"]
    detail = ok(director.get(f"/api/tickets/{closed['id']}"))
    assert detail["status"] == "waiting_on_organizer" and detail["auto_close_at"] is None


def test_failed_required_reply_does_not_start_auto_close_timer(director):
    ticket = create(director)
    ok(director.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "Need clarification.", "request_id": str(uuid4())}))
    with SessionLocal() as db:
        outbound = db.scalar(select(Outbound).where(Outbound.related_ticket_id == ticket["id"]))
        outbound.simulate_failure = True
        db.commit()
    for _ in range(3):
        with SessionLocal() as db:
            for message in db.scalars(select(Outbound).where(Outbound.status == "queued")):
                message.available_at = now() - timedelta(seconds=1)
            db.commit()
        while run_once("failed-ticket"): pass
    assert ok(director.get(f"/api/tickets/{ticket['id']}"))["auto_close_at"] is None


def test_forward_to_requester_does_not_bypass_chair_approval(director):
    login(director, "competitions")
    ticket = create(director)
    original = ok(director.get(f"/api/tickets/{ticket['id']}/messages"))["items"][0]
    assert director.post(f"/api/tickets/{ticket['id']}/messages/{original['id']}/forward", json={"recipient_email": ticket["requester_email"]}).status_code == 403
