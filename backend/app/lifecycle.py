"""Deposit lifecycle rules, field comparison and reminders. The daily sweep is called by a scheduler (Inngest later)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, Deposit, Notification

STATUSES = [
    "SUBMITTED",
    "VERIFIED",
    "DISCREPANCY",
    "ACTIVE",
    "EXPIRING",
    "MATURED",
    "RENEWED",
    "RELEASE_REQUESTED",
    "RELEASED",
    "REJECTED",
]

# Statuses the daily sweep may move between ACTIVE / EXPIRING / MATURED.
TRACKED = {"VERIFIED", "ACTIVE", "EXPIRING", "MATURED"}
# Statuses that still need reminders about maturity.
REMINDED = {"VERIFIED", "ACTIVE", "EXPIRING"}

EXPIRY_WINDOW_DAYS = 30
REMINDER_DAYS = (60, 30, 7)

# Fields that are compared between submitted and bank-confirmed values.
COMPARED_FIELDS = ("reference_no", "bank_name", "amount", "issue_date", "maturity_date")


def lifecycle_status(current: str, maturity: date, today: date) -> str:
    """Status a deposit should have on `today`. Statuses outside TRACKED are returned unchanged."""
    if current not in TRACKED:
        return current
    if maturity < today:
        return "MATURED"
    if (maturity - today).days <= EXPIRY_WINDOW_DAYS:
        return "EXPIRING"
    return "ACTIVE"


def mismatched_fields(dep: Deposit) -> list[str]:
    """Fields where the bank-confirmed value exists and differs from the submitted value."""
    mismatches = []
    for field in COMPARED_FIELDS:
        confirmed = getattr(dep, f"confirmed_{field}")
        if confirmed is None:
            continue
        if confirmed != getattr(dep, field):
            mismatches.append(field)
    return mismatches


def _notify_once(db: Session, dep: Deposit, kind: str, role: str, message: str) -> int:
    """Create a notification unless one of this kind already exists for the deposit. Returns 1 if created."""
    exists = db.scalar(
        select(Notification.id).where(Notification.deposit_id == dep.id, Notification.kind == kind)
    )
    if exists is not None:
        return 0
    db.add(Notification(deposit_id=dep.id, kind=kind, role=role, message=message))
    return 1


def _notifications_for(db: Session, dep: Deposit, today: date) -> int:
    created = 0
    days_left = (dep.effective_maturity - today).days
    if dep.status in REMINDED:
        for threshold in REMINDER_DAYS:
            if 0 <= days_left <= threshold:
                created += _notify_once(
                    db,
                    dep,
                    f"REMINDER_{threshold}",
                    "INSTITUTION_USER",
                    f"FDR {dep.reference_no} matures in {days_left} days ({dep.effective_maturity.isoformat()}).",
                )
    if dep.status == "MATURED" and days_left < 0:
        created += _notify_once(
            db,
            dep,
            "OVERDUE",
            "APPROVING_AUTHORITY",
            f"FDR {dep.reference_no} matured on {dep.effective_maturity.isoformat()} with no renewal or release.",
        )
    return created


def lifecycle_sweep(db: Session, today: date) -> dict:
    """Update statuses and create reminders for `today`. Returns counts of changes made."""
    changed = 0
    notifications = 0
    deposits = db.scalars(select(Deposit).where(Deposit.status.in_(TRACKED | REMINDED))).all()
    for dep in deposits:
        new_status = lifecycle_status(dep.status, dep.effective_maturity, today)
        if new_status != dep.status:
            db.add(
                AuditLog(
                    entity="deposit",
                    entity_id=dep.id,
                    action="LIFECYCLE",
                    actor="system",
                    detail=f"{dep.status} -> {new_status} (as of {today.isoformat()})",
                )
            )
            dep.status = new_status
            changed += 1
        notifications += _notifications_for(db, dep, today)
    db.commit()
    return {"changed": changed, "notifications_created": notifications}
