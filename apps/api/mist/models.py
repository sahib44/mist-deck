import uuid
from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Sequence,
    Float,
    LargeBinary,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, now


class Record:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class User(Record, Base):
    __tablename__ = "users"
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40))
    permissions: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class Session(Record, Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class Catalog(Record):
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Committee(Catalog, Base):
    __tablename__ = "committees"


class Category(Catalog, Base):
    __tablename__ = "competition_categories"


class Qualification(Catalog, Base):
    __tablename__ = "qualification_tags"


class Judge(Record, Base):
    __tablename__ = "judge_contacts"
    first_name: Mapped[str] = mapped_column(String(200), default="")
    last_name: Mapped[str] = mapped_column(String(200), default="")
    display_name: Mapped[str] = mapped_column(String(400), index=True)
    primary_email: Mapped[str] = mapped_column(String(254), default="", index=True)
    alternate_email: Mapped[str] = mapped_column(String(254), default="", index=True)
    preserved_emails: Mapped[list] = mapped_column(JSONB, default=list)
    organization: Mapped[str] = mapped_column(String(300), default="", index=True)
    job_title: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(40), default="prospective", index=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="manual")
    last_contacted_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("judge_contacts.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class JudgeQualification(Base):
    __tablename__ = "judge_qualifications"
    judge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judge_contacts.id"), primary_key=True
    )
    qualification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("qualification_tags.id"), primary_key=True, index=True
    )
    proficiency: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class JudgeCategory(Base):
    __tablename__ = "judge_category_eligibility"
    judge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judge_contacts.id"), primary_key=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competition_categories.id"), primary_key=True, index=True
    )
    eligibility_status: Mapped[str] = mapped_column(String(40), default="eligible")
    notes: Mapped[str] = mapped_column(Text, default="")


class Engagement(Record, Base):
    __tablename__ = "judge_engagements"
    judge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judge_contacts.id"), index=True
    )
    event_year: Mapped[int] = mapped_column(Integer, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competition_categories.id")
    )
    outcome: Mapped[str] = mapped_column(String(40), default="served")
    notes: Mapped[str] = mapped_column(Text, default="")


class PilotCompetition(Record, Base):
    __tablename__ = "pilot_competitions"
    name: Mapped[str] = mapped_column(String(200))
    event_year: Mapped[int] = mapped_column(Integer, index=True)
    category_slug: Mapped[str] = mapped_column(String(80), index=True, default="group-projects")
    is_pilot: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


Index(
    "uq_active_competition_name_year",
    func.lower(PilotCompetition.__table__.c.name),
    PilotCompetition.__table__.c.event_year,
    unique=True,
    postgresql_where=PilotCompetition.__table__.c.deleted_at.is_(None),
)


class PilotNomination(Record, Base):
    __tablename__ = "pilot_nominations"
    pilot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pilot_competitions.id"), index=True
    )
    judge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("judge_contacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="to_contact", index=True)
    qualification_text: Mapped[str] = mapped_column(Text, default="")
    last_contacted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("pilot_id", "judge_id"),)


class PilotDocument(Record, Base):
    __tablename__ = "pilot_documents"
    pilot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pilot_competitions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("pilot_id", "kind"),)


class ImportBatch(Record, Base):
    __tablename__ = "import_batches"
    filename: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Record, Base):
    __tablename__ = "import_rows"
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_batches.id"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSONB)
    normalized_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    resolution: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    matched_judge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("judge_contacts.id")
    )
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    field_decisions: Mapped[dict] = mapped_column(JSONB, default=dict)


class Duplicate(Record, Base):
    __tablename__ = "duplicate_candidates"
    import_row_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_rows.id"), index=True
    )
    existing_judge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("judge_contacts.id")
    )
    existing_row_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_rows.id")
    )
    match_type: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(String(40), default="pending", index=True)


class MergeEvent(Record, Base):
    __tablename__ = "contact_merge_events"
    survivor_judge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judge_contacts.id"), index=True
    )
    merged_judge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("judge_contacts.id")
    )
    import_row_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_rows.id")
    )
    before_snapshot: Mapped[dict] = mapped_column(JSONB)
    after_snapshot: Mapped[dict] = mapped_column(JSONB)
    field_decisions: Mapped[dict] = mapped_column(JSONB)
    merged_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    merged_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class Campaign(Record, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(200))
    subject_template: Mapped[str] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text)
    variables: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    pilot_competition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pilot_competitions.id"), index=True
    )


class CampaignAttachment(Record, Base):
    __tablename__ = "campaign_attachments"
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Recipient(Record, Base):
    __tablename__ = "campaign_recipients"
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id"), index=True
    )
    judge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("judge_contacts.id", ondelete="SET NULL"), index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(400), default="")
    recipient_email: Mapped[str] = mapped_column(String(254))
    rendered_subject: Mapped[str] = mapped_column(Text)
    rendered_body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("campaign_id", "judge_id"),
        UniqueConstraint("campaign_id", "recipient_email"),
    )


ticket_sequence = Sequence("ticket_number_seq")


class Ticket(Record, Base):
    __tablename__ = "tickets"
    public_number: Mapped[str] = mapped_column(String(30), unique=True)
    requester_name: Mapped[str] = mapped_column(String(200))
    requester_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    auto_close_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    last_message_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Outbound(Record, Base):
    __tablename__ = "outbound_messages"
    recipient_email: Mapped[str] = mapped_column(String(254))
    recipient_name: Mapped[str] = mapped_column(String(400))
    subject: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    related_campaign_recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_recipients.id"), unique=True
    )
    related_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tickets.id"), index=True
    )
    forwarded_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    provider_message_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
    claimed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    simulate_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_outbound_claim", "status", "available_at"),)


class TicketMessage(Record, Base):
    __tablename__ = "ticket_messages"
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(40))
    sender_name: Mapped[str] = mapped_column(String(200))
    sender_email: Mapped[str] = mapped_column(String(254))
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id")
    )


class TicketNote(Record, Base):
    __tablename__ = "ticket_internal_notes"
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="internal")
    request_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Audit(Record, Base):
    __tablename__ = "audit_events"
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    summary: Mapped[str] = mapped_column(Text)
    before_data: Mapped[dict | None] = mapped_column(JSONB)
    after_data: Mapped[dict | None] = mapped_column(JSONB)


class InboundMessage(Record, Base):
    __tablename__ = "inbound_messages"
    judge_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("judge_contacts.id", ondelete="SET NULL"), index=True)
    campaign_recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaign_recipients.id"), index=True)
    competition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pilot_competitions.id"), index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    sender_name: Mapped[str] = mapped_column(String(400))
    sender_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    request_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class Notification(Record, Base):
    __tablename__ = "notifications"
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, default="")
    href: Mapped[str] = mapped_column(Text)
    judge_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("judge_contacts.id", ondelete="SET NULL"), index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    outbound_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outbound_messages.id"), unique=True)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ticket_drafts.id"), index=True)
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class DirectoryBackup(Record, Base):
    __tablename__ = "directory_backups"
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    fingerprint: Mapped[str] = mapped_column(String(64))
    judge_count: Mapped[int] = mapped_column(Integer)
    cleared_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class TicketDraft(Record, Base):
    __tablename__ = "ticket_drafts"
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text, default="")
    target_status: Mapped[str] = mapped_column(String(40), default="")
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    base_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class TicketAction(Record, Base):
    __tablename__ = "ticket_actions"
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    signature: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
