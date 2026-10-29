"""SMS alerts for India (DLT-compliant), sent through MSG91's Flow API.

Behaviour mirrors email_service.py:
- Every SMS is first written to the sms_log table (status QUEUED).
- If MSG91_AUTH_KEY and MSG91_FLOW_ID are set, queued messages are sent and marked SENT or FAILED.
- Otherwise they are only marked LOGGED and nothing leaves the server (safe for local development).

DLT rule: in India, SMS text must match a template registered with the telecom operator, so free text
is not allowed. Register ONE template with two variables, for example:

    AICTE FDR Portal: FDR {#var#} {#var#}. Log in to the portal for details.

and create a MSG91 Flow for it. VAR1 carries the FDR reference number and VAR2 a short status phrase
(for example "matures in 7 days"). Keep both short: DLT variables are length-limited (about 30 characters).
"""

import logging
import os
import re
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SmsLog, User

log = logging.getLogger("fdr.sms")

MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow/"
MAX_VAR_LEN = 30


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Returns an Indian mobile number as 91XXXXXXXXXX, or None if it is not a valid one."""
    if not raw:
        return None
    digits = re.sub(r"[\s\-()+]", "", raw)
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if re.fullmatch(r"[6-9]\d{9}", digits):
        return "91" + digits
    return None


def short_var(text: str) -> str:
    """Trims a template variable to the DLT length limit."""
    text = " ".join(text.split())
    return text[:MAX_VAR_LEN].rstrip()  # plain ASCII only: a non-GSM character would switch the SMS to costlier UCS-2


def queue_sms_for_role(
    db: Session, role: str, reference_no: str, status_text: str, institution_id: Optional[int] = None
) -> int:
    """Queue one SMS per active user with this role who has a valid phone number.

    Institution users are only texted about their own institution's FDRs (pass institution_id).
    """
    query = select(User).where(User.role == role, User.is_active.is_(True), User.phone.is_not(None))
    if role == "INSTITUTION_USER":
        query = query.where(User.institution_id == institution_id)
    users = db.scalars(query).all()
    queued = 0
    for user in users:
        number = normalize_phone(user.phone)
        if number is None:
            continue
        # Stored as "<ref>|<status>" so the sender can fill VAR1 and VAR2 without parsing free text.
        db.add(SmsLog(to_number=number, message=f"{short_var(reference_no)}|{short_var(status_text)}", status="QUEUED"))
        queued += 1
    db.flush()
    return queued


def deliver_queued_sms(db: Session) -> dict:
    """Send queued SMS. Without MSG91 settings they are marked LOGGED and nothing leaves the server."""
    auth_key = os.getenv("MSG91_AUTH_KEY")
    flow_id = os.getenv("MSG91_FLOW_ID")
    sender = os.getenv("MSG91_SENDER_ID", "")
    live = bool(auth_key and flow_id)
    counts = {"sent": 0, "failed": 0, "logged": 0}

    for row in db.scalars(select(SmsLog).where(SmsLog.status == "QUEUED")).all():
        if not live:
            row.status = "LOGGED"
            counts["logged"] += 1
            continue
        var1, _, var2 = row.message.partition("|")
        payload: dict = {
            "flow_id": flow_id,
            "recipients": [{"mobiles": row.to_number, "VAR1": var1, "VAR2": var2}],
        }
        if sender:
            payload["sender"] = sender
        try:
            response = httpx.post(
                MSG91_FLOW_URL,
                headers={"authkey": auth_key, "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            body = response.json() if response.content else {}
            if response.status_code == 200 and body.get("type") == "success":
                row.status = "SENT"
                counts["sent"] += 1
            else:
                row.status = "FAILED"
                row.error = f"MSG91 returned HTTP {response.status_code}: {str(body)[:200]}"
                counts["failed"] += 1
        except (httpx.HTTPError, ValueError) as exc:
            row.status = "FAILED"
            row.error = str(exc)[:250]
            counts["failed"] += 1
            log.warning("SMS delivery failed: %s", exc)

    db.commit()
    return counts
