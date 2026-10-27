"""Deposit lifecycle rules. Pure functions plus one sweep that a scheduled job (Inngest later) calls daily."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, Deposit

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

# Statuses the daily sweep is allowed to move between ACTIVE / EXPIRING / MATURED.
TRACKED = {"VERIFIED", "ACTIVE", "EXPIRING", "MATURED"}

EXPIRY_WINDOW_DAYS = 30


def lifecycle_status(current: str, maturity: date, today: date) -> str:
    """Return the status a deposit should have on `today`. Untracked statuses are returned unchanged."""
    if current not in TRACKED:
        return current
    if maturity < today:
        return "MATURED"
    if (maturity - today).days <= EXPIRY_WINDOW_DAYS:
        return "EXPIRING"
    return "ACTIVE"


def lifecycle_sweep(db: Session, today: date) -> int:
    """Update every tracked deposit to its correct status for `today`. Returns how many changed."""
    changed = 0
    deposits = db.scalars(select(Deposit).where(Deposit.status.in_(TRACKED))).all()
    for dep in deposits:
        new_status = lifecycle_status(dep.status, dep.maturity_date, today)
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
    db.commit()
    return changed
