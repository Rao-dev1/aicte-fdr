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
