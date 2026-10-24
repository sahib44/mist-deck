import csv
import io
from mist.worker import run_once


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_directory_tracks_competition_response_qualification_and_sheet_order(director):
    arts = ok(director.get("/api/competitions?category_slug=arts&page_size=100"))["items"]
    competition = next(row for row in arts if row["name"] == "2D Art")
    first = ok(director.post(f"/api/competitions/{competition['id']}/judges", json={
        "name": "First Sample", "email": "first@example.org", "qualifications": "Has led youth art workshops for five years.",
    }))
    second = ok(director.post(f"/api/competitions/{competition['id']}/judges", json={
        "name": "Second Sample", "phone": "555-0122", "qualifications": "Experienced local artist.",
    }))
    ok(director.patch(f"/api/competitions/{competition['id']}/judges/{first['id']}", json={"status": "accepted"}))
    rows = ok(director.get(f"/api/judge-directory?competition_id={competition['id']}"))["items"]
    assert [(row["name"], row["status"]) for row in rows] == [
        ("First Sample", "accepted"), ("Second Sample", "to_contact"),
    ]
    assert rows[0]["qualification"] == "Has led youth art workshops for five years."
    assert rows[1]["phone"] == "555-0122"
    assert ok(director.get("/api/judge-directory?status=accepted"))["total"] >= 1
    response = director.get(f"/api/judge-directory/export?competition_id={competition['id']}")
    assert response.status_code == 200
    sheet = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [row["Name"] for row in sheet] == ["First Sample", "Second Sample"]
    assert sheet[0]["Main category"] == "Arts"
    assert sheet[0]["Competition"] == "2D Art"
    assert sheet[0]["Response"] == "accepted"
    assert sheet[0]["Qualification"] == "Has led youth art workshops for five years."
    assert second["id"] != first["id"]


def test_campaign_attachment_and_sandbox_forward(director):
    arts = ok(director.get("/api/competitions?category_slug=arts&page_size=100"))["items"]
    competition = next(row for row in arts if row["name"] == "3D Art")
    ok(director.post(f"/api/competitions/{competition['id']}/judges", json={
        "name": "Attachment Sample", "email": "attachment@example.org",
    }))
    judge = ok(director.get(f"/api/competitions/{competition['id']}/judges"))["items"][0]["judge"]
    campaign = ok(director.post("/api/campaigns", json={
        "name": "Art invite", "subject_template": "Invitation", "body_template": "Hello {{judge_name}}",
        "judge_ids": [judge["id"]], "pilot_competition_id": competition["id"],
    }))
    url = f"/api/campaigns/{campaign['id']}/attachments"
    assert director.post(url, files={"file": ("run.exe", b"MZbad", "application/octet-stream")}).status_code == 400
    attachment = ok(director.post(url, files={"file": ("rules.pdf", b"%PDF-1.4\n%mock", "application/pdf")}))
    assert [a["filename"] for a in ok(director.get(f"/api/campaigns/{campaign['id']}"))["attachments"]] == ["rules.pdf"]
    assert director.get(f"{url}/{attachment['id']}").content.startswith(b"%PDF-")
    for transition in ("submit", "approve", "queue"):
        ok(director.post(f"/api/campaigns/{campaign['id']}/{transition}"))
    assert director.post(url, files={"file": ("later.txt", b"too late", "text/plain")}).status_code == 400
    run_once("attachment-test")
    original = ok(director.get(f"/api/outbox?campaign_id={campaign['id']}"))["items"][0]
    assert original["status"] == "sent"
    assert original["attachments"][0]["filename"] == "rules.pdf"
    forwarded = ok(director.post(f"/api/outbox/{original['id']}/forward", json={
        "recipient_email": "registration@example.com", "note": "Please review.",
    }))
    assert forwarded["forwarded_from_id"] == original["id"]
    assert forwarded["attachments"][0]["id"] == attachment["id"]
    assert director.get(f"/api/outbox/{forwarded['id']}/attachments/{attachment['id']}").content.startswith(b"%PDF-")
    run_once("forward-test")
    sent = ok(director.get("/api/outbox?q=registration%40example.com"))["items"][0]
    assert sent["status"] == "sent"
    assert "Please review." in sent["body_text"]
