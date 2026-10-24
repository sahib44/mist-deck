from datetime import timedelta
from uuid import UUID
from mist.db import SessionLocal, now
from mist.models import Audit, PilotNomination
from mist.worker import run_once


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_pilot_folder_judges_documents_filters_and_individual_mock_messages(director):
    pilot = ok(director.post(
        "/api/competitions",
        data={"name": "MIST-hack", "event_year": "2027", "category_slug": "group-projects"},
        files={"rules": ("rules.pdf", b"%PDF-1.4\n%mock", "application/pdf")},
    ))
    pilot_id = pilot["id"]
    assert pilot["name"] == "MIST-hack"
    assert pilot["counts"] == {}
    assert pilot["documents"][0]["filename"] == "rules.pdf"
    doc = director.get(f"/api/competitions/{pilot_id}/documents/rules")
    assert doc.status_code == 200 and doc.content.startswith(b"%PDF-")
    assert director.get(f"/api/competitions/{pilot_id}/documents/procedures").status_code == 404
    ok(director.put(
        f"/api/competitions/{pilot_id}/documents/procedures",
        files={"file": ("procedures.pdf", b"%PDF-1.4\n%mock", "application/pdf")},
    ))

    nominations = []
    for number in range(3):
        item = ok(director.post(f"/api/competitions/{pilot_id}/judges", json={
            "name": f"Sample Judge {number}",
            "email": f"pilot-{number}@example.edu",
            "phone": f"555-010{number}",
            "qualifications": "Software; Engineering",
        }))
        nominations.append(item)
    assert director.post(f"/api/competitions/{pilot_id}/judges", json={
        "name": "Missing contact", "email": "", "phone": "",
    }).status_code == 400
    phone_only = ok(director.post(f"/api/competitions/{pilot_id}/judges", json={
        "name": "Phone Only", "phone": "555-0199", "qualifications": "Hardware",
    }))
    assert phone_only["status"] == "to_contact"
    assert ok(director.get(f"/api/competitions/{pilot_id}"))["counts"] == {"to_contact": 4}
    first = ok(director.patch(f"/api/competitions/{pilot_id}/judges/{nominations[0]['id']}", json={"status": "accepted"}))
    assert first["responded_at"]
    ok(director.patch(f"/api/competitions/{pilot_id}/judges/{nominations[1]['id']}", json={"status": "awaiting_response"}))
    ok(director.patch(f"/api/competitions/{pilot_id}/judges/{nominations[2]['id']}", json={"status": "declined"}))
    assert ok(director.get(f"/api/competitions/{pilot_id}/judges?status=accepted"))["total"] == 1
    with SessionLocal() as db:
        waiting = db.get(PilotNomination, UUID(nominations[1]["id"]))
        waiting.last_contacted_at = now() - timedelta(days=8)
        db.commit()
    overdue = ok(director.get(f"/api/competitions/{pilot_id}/judges?overdue_days=7"))
    assert overdue["total"] == 1
    assert overdue["items"][0]["id"] == nominations[1]["id"]
    ok(director.patch(f"/api/competitions/{pilot_id}/judges/{nominations[1]['id']}", json={"status": "to_contact"}))
    refreshed = ok(director.patch(f"/api/competitions/{pilot_id}/judges/{nominations[1]['id']}", json={"status": "awaiting_response"}))
    assert refreshed["last_contacted_at"] != overdue["items"][0]["last_contacted_at"]
    assert ok(director.get(f"/api/competitions/{pilot_id}/judges?overdue_days=7"))["total"] == 0
    selected = ok(director.get(f"/api/competitions/{pilot_id}/judges"))["items"]
    ids = [item["judge"]["id"] for item in selected if item["status"] != "declined"]
    campaign = ok(director.post("/api/campaigns", json={
        "name": "Pilot update",
        "subject_template": "Hello {{first_name}}",
        "body_template": "Dear {{judge_name}}, {{category_name}}",
        "judge_ids": ids,
        "pilot_competition_id": pilot_id,
    }))
    assert campaign["recipient_count"] == 2
    previews = ok(director.get(f"/api/campaigns/{campaign['id']}/preview"))["items"]
    assert len({item["recipient_email"] for item in previews}) == 2
    assert all("MIST-hack" in item["rendered_body"] for item in previews)
    for transition in ("submit", "approve", "queue"):
        ok(director.post(f"/api/campaigns/{campaign['id']}/{transition}"))
    run_once("pilot-test")
    run_once("pilot-test")
    outbox = ok(director.get(f"/api/outbox?campaign_id={campaign['id']}"))
    assert outbox["total"] == 2
    assert all(item["status"] == "sent" and item["provider"] == "mock" for item in outbox["items"])
    with SessionLocal() as db:
        assert db.get(PilotNomination, UUID(nominations[0]["id"])).status == "accepted"
        waiting_after_mock = db.get(PilotNomination, UUID(nominations[1]["id"]))
        assert waiting_after_mock.status == "awaiting_response"
        assert waiting_after_mock.last_contacted_at.isoformat() > refreshed["last_contacted_at"]


def test_pilot_documents_and_contacts_require_judge_access(client):
    import os
    ok(client.post("/api/auth/login", json={
        "email": "support@example.com", "password": os.environ["SEED_PASSWORD"]
    }))
    assert client.get("/api/competitions").status_code == 403
    assert client.post("/api/competitions", data={"name": "Private", "event_year": "2027", "category_slug": "group-projects"}).status_code == 403


def test_sandbox_pilot_message_advances_to_contact_and_resets_follow_up_clock(director):
    pilot_id = ok(director.post("/api/competitions", data={
        "name": "Mock outreach", "event_year": "2027", "category_slug": "group-projects",
    }))["id"]
    nomination = ok(director.post(f"/api/competitions/{pilot_id}/judges", json={
        "name": "Sample Outreach Judge", "email": "outreach@example.org",
    }))
    judge_id = ok(director.get(f"/api/competitions/{pilot_id}/judges"))["items"][0]["judge"]["id"]
    campaign_id = ok(director.post("/api/campaigns", json={
        "name": "Pilot invitation",
        "subject_template": "Invitation",
        "body_template": "Hello {{judge_name}}",
        "judge_ids": [judge_id],
        "pilot_competition_id": pilot_id,
    }))["id"]
    for transition in ("submit", "approve", "queue"):
        ok(director.post(f"/api/campaigns/{campaign_id}/{transition}"))
    assert ok(director.get(f"/api/competitions/{pilot_id}/judges"))["items"][0]["status"] == "to_contact"
    run_once("pilot-auto-status")
    after = ok(director.get(f"/api/competitions/{pilot_id}/judges"))["items"][0]
    assert after["id"] == nomination["id"]
    assert after["status"] == "awaiting_response"
    assert after["last_contacted_at"]
    assert ok(director.get(f"/api/competitions/{pilot_id}/judges?overdue_days=7"))["total"] == 0
    assert ok(director.get(f"/api/outbox?campaign_id={campaign_id}"))["items"][0]["provider"] == "mock"


def test_competition_categories_and_pilot_only_deletion(director):
    category_response = director.get("/api/competitions/categories")
    assert category_response.status_code == 200
    categories = category_response.json()
    assert {item["slug"] for item in categories} == {
        "arts", "knowledge-quran", "writing-oratory", "brackets", "group-projects", "sports-referees",
    }
    arts = ok(director.get("/api/competitions?category_slug=arts&page_size=100"))["items"]
    fixed = next(item for item in arts if item["name"] == "2D Art")
    culinary = next(item for item in arts if item["name"] == "Culinary Arts")
    assert fixed["is_pilot"] is False
    assert culinary["is_pilot"] is True
    confirmations = {"confirmed_first": True, "confirmed_second": True, "exact_name": "2D Art"}
    assert director.request("DELETE", f"/api/competitions/{fixed['id']}", json=confirmations).status_code == 403
    assert director.get(f"/api/competitions/{fixed['id']}").status_code == 200
    assert director.request("DELETE", f"/api/competitions/{culinary['id']}", json={
        **confirmations, "exact_name": "Culinary Arts", "confirmed_second": False,
    }).status_code == 400
    assert director.request("DELETE", f"/api/competitions/{culinary['id']}", json={
        **confirmations, "exact_name": "culinary arts",
    }).status_code == 400
    assert director.request("DELETE", f"/api/competitions/{culinary['id']}", json={
        **confirmations, "exact_name": "Culinary Arts",
    }).status_code == 200
    assert director.get(f"/api/competitions/{culinary['id']}").status_code == 404
    assert all(item["id"] != culinary["id"] for item in ok(director.get("/api/competitions?category_slug=arts&page_size=100"))["items"])
    with SessionLocal() as db:
        event = db.query(Audit).filter(Audit.action == "pilot.deleted", Audit.entity_id == culinary["id"]).one()
        assert event.actor_user_id is not None
    deletions = ok(director.get("/api/competitions/deletions"))["items"]
    assert any(item["id"] == culinary["id"] and item["deleted_by_name"] == "Demo Director" for item in deletions)
    import os
    ok(director.post("/api/auth/login", json={
        "email": "competitions@example.com", "password": os.environ["SEED_PASSWORD"],
    }))
    assert any(item["id"] == culinary["id"] for item in ok(director.get("/api/competitions/deletions"))["items"])
    replacement = ok(director.post("/api/competitions", data={
        "name": "Culinary Arts", "event_year": "2027", "category_slug": "arts",
    }))
    assert replacement["id"] != culinary["id"]
    assert replacement["is_pilot"] is True
