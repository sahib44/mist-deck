import os
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from mist.db import SessionLocal, now
from mist.models import Judge, Recipient, Outbound, Notification, DirectoryBackup, Audit
from mist.worker import run_once


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def sign_in(client, account):
    return ok(client.post("/api/auth/login", json={"email": f"{account}@example.com", "password": os.environ["SEED_PASSWORD"]}))


def campaign(client, **extra):
    return ok(client.post("/api/campaigns", json={"name": "Team outreach", "subject_template": "Invitation", "body_template": "Hello {{judge_name}}", **extra}))


def send(client, item):
    for action in ("submit", "approve", "queue"):
        ok(client.post(f"/api/campaigns/{item['id']}/{action}"))
    while run_once("team-test"):
        pass


def receive(client, address, **extra):
    return ok(client.post("/api/inbox/simulate", json={"sender_email": address, "sender_name": "Sample Sender", "subject": "Re: Invitation", "body": "Thanks, I can judge.", "request_id": str(uuid4()), **extra}))


def test_chair_member_and_director_deletion_permissions(client):
    member = sign_in(client, "competitions")
    assert member["role"] == "competitions_member"
    culinary = next(p for p in ok(client.get("/api/competitions?category_slug=arts"))["items"] if p["is_pilot"])
    payload = {"confirmed_first": True, "confirmed_second": True, "exact_name": culinary["name"]}
    assert client.request("DELETE", f"/api/competitions/{culinary['id']}", json=payload).status_code == 403
    assert client.post("/api/judge-directory/clear/prepare").status_code == 403
    assert client.post("/api/judge-directory/clear", json={"confirmed_first": True, "confirmed_second": True, "password": os.environ["SEED_PASSWORD"], "backup_id": str(uuid4())}).status_code == 403
    chair = sign_in(client, "chair")
    assert chair["role"] == "competitions_chair"
    fixed = next(p for p in ok(client.get("/api/competitions?category_slug=arts"))["items"] if not p["is_pilot"])
    assert client.request("DELETE", f"/api/competitions/{fixed['id']}", json={**payload, "exact_name": fixed["name"]}).status_code == 403
    ok(client.request("DELETE", f"/api/competitions/{culinary['id']}", json=payload))
    assert any(row["deleted_by_name"] == "Competitions Chair" for row in ok(client.get("/api/competitions/deletions"))["items"])


def test_direct_recipients_are_validated_deduplicated_and_saved_only_on_request(director):
    before = ok(director.get("/api/judges"))["total"]
    invalid = director.post("/api/campaigns", json={"name": "Invalid", "subject_template": "Test", "body_template": "Test", "recipients": [{"email": "invalid"}]})
    assert invalid.status_code == 400
    item = campaign(director, recipients=[{"name": "External Person", "email": "outside@sample.invalid"}, {"name": "New Judge", "email": "judge@sample.invalid", "add_to_directory": True}, {"name": "Duplicate", "email": "OUTSIDE@sample.invalid"}])
    assert item["recipient_count"] == 2
    assert len(item["excluded"]) == 1
    assert ok(director.get("/api/judges"))["total"] == before + 1
    assert not ok(director.get("/api/judges?q=outside%40sample.invalid"))["items"]
    search = ok(director.get("/api/recipient-search?q=New%20Judge"))
    assert search[0]["email"] == "judge@sample.invalid"
    send(director, item)
    preview = ok(director.get(f"/api/campaigns/{item['id']}/preview"))["items"]
    assert {r["recipient_name"] for r in preview} == {"External Person", "New Judge"}
    assert all(r["status"] == "sent" for r in preview)
    assert ok(director.get("/api/campaigns?q=outside%40sample.invalid"))["total"] == 1
    assert director.get("/api/saved-lists").status_code == 404


def test_reply_marks_only_related_competition_and_read_clears_shared_alerts(director):
    competitions = ok(director.get("/api/competitions?category_slug=arts"))["items"]
    first, other = [p for p in competitions if not p["is_pilot"]][:2]
    nomination = ok(director.post(f"/api/competitions/{first['id']}/judges", json={"name": "Unread Judge", "email": "unread@example.org"}))
    ok(director.post(f"/api/competitions/{other['id']}/judges", json={"name": "Unread Judge", "existing_judge_id": nomination["judge_id"]}))
    item = campaign(director, judge_ids=[nomination["judge_id"]], pilot_competition_id=first["id"])
    send(director, item)
    assert ok(director.get(f"/api/competitions/{first['id']}/judges"))["items"][0]["status"] == "awaiting_response"
    sign_in(director, "competitions")
    received = receive(director, "unread@example.org")
    assert received["judge_id"] == nomination["judge_id"]
    assert ok(director.get("/api/competitions/categories"))[0]["unread_count"] == 1
    assert ok(director.get(f"/api/competitions/{first['id']}"))["unread_count"] == 1
    assert ok(director.get(f"/api/competitions/{other['id']}"))["unread_count"] == 0
    assert ok(director.get(f"/api/competitions/{first['id']}/judges"))["items"][0]["unread_count"] == 1
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    conversation = ok(director.get(f"/api/conversations/judges/{nomination['judge_id']}"))
    assert len(conversation["messages"]) == 2
    assert conversation["unread_count"] == 1
    notification = ok(director.get("/api/notifications"))["items"][0]
    ok(director.post(f"/api/notifications/{notification['id']}/read"))
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    ok(director.post(f"/api/conversations/judges/{nomination['judge_id']}/read", json={"read_through": conversation["read_through"]}))
    assert ok(director.get(f"/api/competitions/{first['id']}"))["unread_count"] == 0
    assert ok(director.get("/api/notifications"))["unread_count"] == 0
    # A later reply survives an older read cursor.
    receive(director, "unread@example.org")
    ok(director.post(f"/api/conversations/judges/{nomination['judge_id']}/read", json={"read_through": conversation["read_through"]}))
    assert ok(director.get("/api/notifications"))["unread_count"] == 1


def test_nonjudge_email_becomes_ticket_without_creating_judge_and_is_idempotent(director):
    before = ok(director.get("/api/judges"))["total"]
    token = str(uuid4())
    first = receive(director, "not-a-judge@sample.invalid", request_id=token)
    second = receive(director, "not-a-judge@sample.invalid", request_id=token)
    assert first["ticket_id"] == second["ticket_id"]
    assert ok(director.get("/api/tickets"))["total"] == 1
    assert ok(director.get("/api/judges"))["total"] == before
    sign_in(director, "competitions")
    assert ok(director.get("/api/tickets"))["total"] == 1
    assert ok(director.get("/api/notifications"))["items"][0]["ticket_id"] == first["ticket_id"]
    assert ok(director.get("/api/conversations"))["total"] == 0


def test_failed_recipient_notification_identifies_exact_email(director):
    item = campaign(director, recipients=[{"name": "Success", "email": "success@example.com"}, {"name": "Failed Person", "email": "fails@example.com"}])
    for action in ("submit", "approve", "queue"):
        ok(director.post(f"/api/campaigns/{item['id']}/{action}"))
    with SessionLocal() as db:
        message = db.scalar(select(Outbound).where(Outbound.recipient_email == "fails@example.com"))
        message.simulate_failure = True
        db.commit()
    for _ in range(3):
        with SessionLocal() as db:
            for message in db.scalars(select(Outbound).where(Outbound.status == "queued")):
                message.available_at = now() - timedelta(seconds=1)
            db.commit()
        while run_once("failure-test"):
            pass
    detail = ok(director.get(f"/api/campaigns/{item['id']}"))
    assert detail["status"] == "partially_failed"
    assert detail["failed_recipients"][0]["recipient_email"] == "fails@example.com"
    alerts = ok(director.get("/api/notifications"))["items"]
    assert len(alerts) == 1
    assert "fails@example.com" in alerts[0]["body"]
    assert "Failed Person" in alerts[0]["title"]


def test_clear_requires_backup_confirmations_password_and_preserves_mail_history(director):
    sign_in(director, "chair")
    judge = ok(director.get("/api/judges"))["items"][0]
    item = campaign(director, judge_ids=[judge["id"]])
    send(director, item)
    backup = ok(director.post("/api/judge-directory/clear/prepare"))
    sheet = director.get(backup["download_url"])
    assert sheet.status_code == 200 and judge["display_name"] in sheet.text
    body = {"confirmed_first": True, "confirmed_second": True, "password": os.environ["SEED_PASSWORD"], "backup_id": backup["id"]}
    assert director.post("/api/judge-directory/clear", json={**body, "password": "wrong"}).status_code == 403
    assert director.post("/api/judge-directory/clear", json={**body, "confirmed_second": False}).status_code == 400
    result = ok(director.post("/api/judge-directory/clear", json=body))
    assert result["cleared"] == backup["judge_count"]
    assert ok(director.get("/api/judges"))["total"] == 0
    assert ok(director.get("/api/judge-directory"))["total"] == 0
    assert ok(director.get(f"/api/campaigns/{item['id']}"))["recipient_count"] == 1
    preview = ok(director.get(f"/api/campaigns/{item['id']}/preview"))["items"][0]
    assert preview["judge_id"] is None and preview["recipient_name"] == judge["display_name"]
    assert director.get(backup["download_url"]).content == sheet.content
    assert director.post("/api/judge-directory/clear", json=body).status_code == 400
    with SessionLocal() as db:
        event = db.scalar(select(Audit).where(Audit.action == "judges.cleared"))
        assert event.actor_user_id is not None


def test_clear_rejects_stale_backup_when_directory_changes(director):
    backup = ok(director.post("/api/judge-directory/clear/prepare"))
    ok(director.post("/api/judges", json={"display_name": "Later Judge", "primary_email": "later@example.com"}))
    response = director.post("/api/judge-directory/clear", json={"confirmed_first": True, "confirmed_second": True, "password": os.environ["SEED_PASSWORD"], "backup_id": backup["id"]})
    assert response.status_code == 409
    assert ok(director.get("/api/judges"))["total"] > 0


def test_shared_ticket_notifications_visible_to_heads_and_restricted_for_tech(director):
    ticket = ok(director.post("/api/tickets", json={"requester_name": "Private Requester", "requester_email": "private@example.org", "subject": "Private general ticket", "body": "For directors only."}))
    ok(director.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "Private reply", "request_id": str(uuid4())}))
    with SessionLocal() as db:
        message = db.scalar(select(Outbound).where(Outbound.related_ticket_id == ticket["id"]))
        message.simulate_failure = True
        db.commit()
    for _ in range(3):
        with SessionLocal() as db:
            for message in db.scalars(select(Outbound).where(Outbound.status == "queued")):
                message.available_at = now() - timedelta(seconds=1)
            db.commit()
        while run_once("private-failure"):
            pass
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    sign_in(director, "competitions")
    assert ok(director.get("/api/notifications"))["unread_count"] == 1
    sign_in(director, "tech")
    assert ok(director.get("/api/notifications"))["items"] == []


def test_nonjudge_reply_joins_the_shared_competitions_ticket(director):
    private = ok(director.post("/api/tickets", json={"requester_name": "Private", "requester_email": "same-sender@example.org", "subject": "Private question", "body": "Director only"}))
    sign_in(director, "competitions")
    received = receive(director, "same-sender@example.org", subject="Re: Private question")
    assert received["ticket_id"] == private["id"]
    assert ok(director.get(f"/api/tickets/{private['id']}/messages"))["total"] == 2
    assert director.get(f"/api/tickets/{received['ticket_id']}").status_code == 200


def test_direct_email_respects_preserved_address_suppression(director):
    judge = ok(director.get("/api/judges"))["items"][0]
    with SessionLocal() as db:
        record = db.get(Judge, judge["id"])
        record.preserved_emails = ["old-address@example.org"]
        record.do_not_contact = True
        db.commit()
    response = director.post("/api/campaigns", json={"name": "Suppression", "subject_template": "Test", "body_template": "Test", "recipients": [{"email": "old-address@example.org"}]})
    assert response.status_code == 400
    assert ok(director.get("/api/campaigns"))["total"] == 0
