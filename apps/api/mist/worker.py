"""PostgreSQL queue and sandbox-only delivery. No network email transport exists."""

import json
import logging
import socket
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Protocol
from sqlalchemy import select, or_, and_
from .db import SessionLocal, now
from .models import Outbound, Recipient, Campaign, Judge, PilotNomination
from .services import contact_email, audit

log = logging.getLogger("mist.worker")


class EmailProvider(Protocol):
    def send(self, message: Outbound) -> str: ...


class MockEmailProvider:
    def send(self, message):
        # A mock receipt only. This provider has no network transport.
        contact_email(message.recipient_email)
        if message.simulate_failure:
            raise RuntimeError("Simulated sandbox delivery failure")
        # Database identity is the delivery receipt. Transaction retries cannot produce a second message.
        return f"mock-{message.idempotency_key}"


def aggregate(db, campaign):
    db.flush()
    states = list(
        db.scalars(select(Recipient.status).where(Recipient.campaign_id == campaign.id))
    )
    if campaign.status == "cancelled":
        return
    if any(s in {"pending", "queued"} for s in states):
        campaign.status = (
            "sending" if any(s in {"sent", "failed"} for s in states) else "queued"
        )
    else:
        campaign.status = "partially_failed" if "failed" in states else "completed"


def claim(db, worker_id):
    stamp = now()
    msg = db.scalar(
        select(Outbound)
        .where(
            or_(
                and_(Outbound.status == "queued", Outbound.available_at <= stamp),
                and_(
                    Outbound.status == "sending",
                    Outbound.claimed_at < stamp - timedelta(minutes=5),
                ),
            )
        )
        .order_by(Outbound.available_at, Outbound.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not msg:
        db.rollback()
        return None
    msg.status, msg.claimed_at, msg.claimed_by = "sending", stamp, worker_id
    db.commit()
    return msg.id


def deliver(db, id, worker_id):
    initial = db.get(Outbound, id)
    if not initial:
        return
    campaign, rec = None, None
    if initial.related_campaign_recipient_id:
        rec = db.get(Recipient, initial.related_campaign_recipient_id)
        campaign = db.scalar(
            select(Campaign).where(Campaign.id == rec.campaign_id).with_for_update()
        )
    msg = db.scalar(
        select(Outbound)
        .where(Outbound.id == id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if msg.status != "sending" or msg.claimed_by != worker_id:
        db.rollback()
        return
    judge = db.get(Judge, rec.judge_id) if rec else None
    if (campaign and campaign.status == "cancelled") or (
        judge and (judge.do_not_contact or judge.merged_into_id)
    ):
        msg.status, msg.last_error = (
            "cancelled",
            "Campaign cancelled or contact suppressed",
        )
        if rec:
            rec.status, rec.failure_reason = "cancelled", msg.last_error
    else:
        msg.attempt_count += 1
        try:
            msg.provider_message_id = MockEmailProvider().send(msg)
            msg.status, msg.completed_at, msg.last_error = "sent", now(), ""
            if rec:
                rec.status, rec.sent_at = "sent", now()
                if campaign.pilot_competition_id:
                    nomination = db.scalar(
                        select(PilotNomination).where(
                            PilotNomination.pilot_id == campaign.pilot_competition_id,
                            PilotNomination.judge_id == judge.id,
                        )
                    )
                    if nomination and nomination.status in {"to_contact", "awaiting_response"}:
                        nomination.status = "awaiting_response"
                        nomination.last_contacted_at = now()
                else:
                    judge.last_contacted_at = now()
        except Exception as exc:
            msg.last_error = (
                "Simulated sandbox delivery failure"
                if msg.simulate_failure
                else "Sandbox recipient validation failed"
            )
            msg.status = "failed" if msg.attempt_count >= 3 else "queued"
            msg.available_at = now() + timedelta(seconds=2**msg.attempt_count)
            if rec:
                rec.status = "failed" if msg.status == "failed" else "queued"
                rec.failure_reason = msg.last_error
        audit(
            db,
            None,
            "message.delivery_attempt",
            msg,
            f"Sandbox attempt {msg.attempt_count}: {msg.status}",
            after={"status": msg.status, "attempt_count": msg.attempt_count},
        )
    msg.claimed_at, msg.claimed_by = None, None
    if campaign:
        aggregate(db, campaign)
    db.commit()
    log.info(
        json.dumps(
            {
                "event": "delivery",
                "message_id": str(id),
                "status": msg.status,
                "attempt": msg.attempt_count,
            }
        )
    )


def run_once(worker_id="manual-worker"):
    with SessionLocal() as db:
        id = claim(db, worker_id)
    if not id:
        return False
    with SessionLocal() as db:
        deliver(db, id, worker_id)
    return True


last_heartbeat = time.monotonic()


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        healthy = time.monotonic() - last_heartbeat < 30
        self.send_response(200 if healthy else 503)
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "ok" if healthy else "stalled"}).encode()
        )

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if "--once" in sys.argv:
        while run_once():
            pass
    else:
        threading.Thread(
            target=HTTPServer(("0.0.0.0", 8001), Health).serve_forever, daemon=True
        ).start()
        worker_id = socket.gethostname()
        while True:
            try:
                worked = run_once(worker_id)
                last_heartbeat = time.monotonic()
                if not worked:
                    time.sleep(1)
            except Exception:
                log.exception("Worker transaction failed; rolled back and will recover")
                time.sleep(2)
