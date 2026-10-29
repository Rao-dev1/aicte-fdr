from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)


class Deposit(Base):
    __tablename__ = "deposits"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)

    # Values submitted by the institution
    reference_no: Mapped[str] = mapped_column(String(100), unique=True)
    bank_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    issue_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date, index=True)

    # Values confirmed by the bank or the officer. NULL means not checked yet.
    confirmed_reference_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confirmed_bank_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confirmed_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    confirmed_issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confirmed_maturity_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    mismatch_fields: Mapped[str] = mapped_column(String(255), default="")  # comma-separated field names

    status: Mapped[str] = mapped_column(String(32), index=True)
    previous_deposit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deposits.id"), nullable=True)

    @property
    def effective_maturity(self) -> date:
        """Bank-confirmed maturity when available, otherwise the submitted one."""
        return self.confirmed_maturity_date or self.maturity_date


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("deposit_id", "kind", name="uq_notification_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # REMINDER_60 / REMINDER_30 / REMINDER_7 / OVERDUE
    role: Mapped[str] = mapped_column(String(32))  # which role should see it
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseRequest(Base):
    __tablename__ = "release_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))  # PENDING / APPROVED / REJECTED
    status_before: Mapped[str] = mapped_column(String(32))  # restored on rejection
    requested_by: Mapped[str] = mapped_column(String(100))
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remarks: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    institution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # stored as 91XXXXXXXXXX


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_address: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)  # QUEUED / LOGGED / SENT / FAILED
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SmsLog(Base):
    __tablename__ = "sms_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_number: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(100))  # "<reference>|<status text>", the two template variables
    status: Mapped[str] = mapped_column(String(16), index=True)  # QUEUED / LOGGED / SENT / FAILED
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(16))  # schedule / catch-up / manual
    status: Mapped[str] = mapped_column(String(16))  # RUNNING / OK / FAILED
    detail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FDRLineageRelation(Base):
    __tablename__ = "fdr_lineage_relations"
    __table_args__ = (
        UniqueConstraint("source_deposit_id", "target_deposit_id", "relation_type", name="uq_lineage_rel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    target_deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), index=True)  # ORIGINAL, RENEWAL, AUTO_RENEWAL, REPLACEMENT, SUPERSEDED, RELEASED_CLOSED
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    actor: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FDRLifecycleEvent(Base):
    __tablename__ = "fdr_lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    actor_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(String(255))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    event_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseReadinessEvaluation(Base):
    __tablename__ = "release_readiness_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    release_request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("release_requests.id"), nullable=True)
    overall_status: Mapped[str] = mapped_column(String(32))  # READY_FOR_APPROVAL, BLOCKED, UNDER_REVIEW, INCOMPLETE
    total_prerequisites: Mapped[int] = mapped_column(Integer, default=0)
    satisfied_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_data_json: Mapped[str] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegulationRule(Base):
    __tablename__ = "regulation_rules"
    __table_args__ = (
        UniqueConstraint("rule_code", "version", name="uq_rule_code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)  # DRAFT, ACTIVE, SUPERSEDED, ARCHIVED
    source_reference: Mapped[str] = mapped_column(String(255))
    rule_spec_json: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AssessmentSnapshot(Base):
    __tablename__ = "assessment_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"), index=True)
    release_request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("release_requests.id"), nullable=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("regulation_rules.id"))
    rule_code: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    assessment_type: Mapped[str] = mapped_column(String(64))  # DEPOSIT_COMPLIANCE, RELEASE_ELIGIBILITY, REPLAY_SIMULATION
    is_replay: Mapped[bool] = mapped_column(Boolean, default=False)
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    evaluation_result: Mapped[str] = mapped_column(String(32))  # COMPLIANT, NON_COMPLIANT, REQUIRES_MANUAL_REVIEW
    conditions_evaluated_json: Mapped[str] = mapped_column(Text)
    assessed_by: Mapped[str] = mapped_column(String(100))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrityFinding(Base):
    __tablename__ = "integrity_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    status: Mapped[str] = mapped_column(String(32), index=True)  # OPEN, UNDER_REVIEW, CONFIRMED_INCONSISTENCY, FALSE_POSITIVE, RESOLVED, ESCALATED
    primary_deposit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deposits.id"), nullable=True, index=True)
    related_deposit_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    institution_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    explanation: Mapped[str] = mapped_column(Text)
    trigger_values_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolution_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IntegrityFindingAction(Base):
    __tablename__ = "integrity_finding_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("integrity_findings.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))  # STATUS_CHANGE, ASSIGN, COMMENT, ESCALATE
    actor: Mapped[str] = mapped_column(String(100))
    actor_role: Mapped[str] = mapped_column(String(32), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
