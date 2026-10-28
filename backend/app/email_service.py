"""Email alerts. Emails are always written to the email_log table. If SENDGRID_API_KEY is set, they are also sent."""

import os

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EmailLog, User

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def queue_for_role(db: Session, role: str, subject: str, body: str) -> int:
    """Queue one email per active user with this role who has an email address."""
    users = db.scalars(
        select(User).where(User.role == role, User.is_active.is_(True), User.email.is_not(None))
    ).all()
    for user in users:
        db.add(EmailLog(to_address=user.email, subject=subject, body=body, status="QUEUED"))
    db.flush()
    return len(users)


def deliver_queued(db: Session) -> dict:
    """Send queued emails. Without a SendGrid key they are marked LOGGED and nothing leaves the server."""
    api_key = os.getenv("SENDGRID_API_KEY")
    sender = os.getenv("EMAIL_FROM", "fdr-portal@example.com")
    counts = {"sent": 0, "failed": 0, "logged": 0}

    for row in db.scalars(select(EmailLog).where(EmailLog.status == "QUEUED")).all():
        if not api_key:
            row.status = "LOGGED"
            counts["logged"] += 1
            continue
        try:
            response = httpx.post(
                SENDGRID_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "personalizations": [{"to": [{"email": row.to_address}]}],
                    "from": {"email": sender},
                    "subject": row.subject,
                    "content": [{"type": "text/plain", "value": row.body}],
                },
                timeout=10,
            )
            if response.status_code == 202:
                row.status = "SENT"
                counts["sent"] += 1
            else:
                row.status = "FAILED"
                row.error = f"SendGrid returned HTTP {response.status_code}"
                counts["failed"] += 1
        except httpx.HTTPError as exc:
            row.status = "FAILED"
            row.error = str(exc)
            counts["failed"] += 1

    db.commit()
    return counts
