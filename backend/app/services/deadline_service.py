"""Smart Deadline & Expiry Alerts Service.

Computes dynamic, explainable deadline events from actual database records:
- FDR maturity & renewal countdowns (30, 15, 7 days, and overdue)
- Pending scrutiny verification tasks
- Outstanding release approvals
- Discrepancy remediation actions

Deduplicates alerts by unique alert keys and respects institutional scope.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor
from ..models import Deposit, Institution, ReleaseRequest
from ..scheduler import today_ist
from ..schemas import DeadlineItem, DeadlinesResponse, DeadlineSummary


def get_deadlines(
    db: Session,
    actor: Actor,
    filter_type: str = "all",
    threshold: str = "all",
    limit: int = 50,
) -> DeadlinesResponse:
    today = today_ist()

    # Preload institution lookup
    institutions = {i.id: i for i in db.scalars(select(Institution)).all()}

    # Base deposit query scoped to institution if needed
    query = select(Deposit)
    if actor.role == "INSTITUTION_USER":
        query = query.where(Deposit.institution_id == actor.institution_id)

    deposits = db.scalars(query).all()

    # Preload release requests
    rel_query = (
        select(ReleaseRequest, Deposit)
        .join(Deposit, ReleaseRequest.deposit_id == Deposit.id)
        .where(ReleaseRequest.status == "PENDING")
    )
    if actor.role == "INSTITUTION_USER":
        rel_query = rel_query.where(Deposit.institution_id == actor.institution_id)

    pending_releases = db.execute(rel_query).all()

    raw_items: list[DeadlineItem] = []
    seen_alert_ids: set[str] = set()

    # 1. Evaluate Deposit Maturity & Renewals
    for dep in deposits:
        inst = institutions.get(dep.institution_id)
        inst_name = inst.name if inst else f"Institution #{dep.institution_id}"
        inst_code = inst.code if inst else "N/A"

        effective_mat = dep.effective_maturity
        days_left = (effective_mat - today).days

        # Determine urgency category
        if dep.status in ("RELEASED", "RENEWED"):
            urgency = "completed"
            label = "FDR Lifecycle Concluded"
            is_my_action = False
            target_role = "ALL"
            deadline_type = "MATURITY"
        elif days_left < 0:
            urgency = "overdue"
            label = f"Matured {abs(days_left)}d Ago — Action Required"
            deadline_type = "RENEWAL"
            target_role = "INSTITUTION_USER" if actor.role == "INSTITUTION_USER" else "REGULATOR_OFFICER"
            is_my_action = actor.role in ("INSTITUTION_USER", "ADMIN")
        elif days_left <= 7:
            urgency = "due_soon"
            label = f"Maturing in {days_left}d (Critical Renewal Window)"
            deadline_type = "MATURITY"
            target_role = "INSTITUTION_USER"
            is_my_action = actor.role in ("INSTITUTION_USER", "ADMIN")
        elif days_left <= 15:
            urgency = "due_soon"
            label = f"Maturing in {days_left}d — Prepare Renewal"
            deadline_type = "MATURITY"
            target_role = "INSTITUTION_USER"
            is_my_action = actor.role in ("INSTITUTION_USER", "ADMIN")
        elif days_left <= 30:
            urgency = "upcoming"
            label = f"Maturing in {days_left}d — 30-Day Window"
            deadline_type = "MATURITY"
            target_role = "INSTITUTION_USER"
            is_my_action = actor.role in ("INSTITUTION_USER", "ADMIN")
        elif days_left <= 90:
            urgency = "upcoming"
            label = f"Scheduled Maturity in {days_left}d"
            deadline_type = "MATURITY"
            target_role = "ALL"
            is_my_action = False
        else:
            urgency = "upcoming"
            label = f"Active FDR (Tenure Active)"
            deadline_type = "MATURITY"
            is_my_action = False
            target_role = "ALL"

        # Only include active/tracked deposits for maturity/renewal alerts unless completed
        if dep.status in ("ACTIVE", "EXPIRING", "MATURED", "VERIFIED", "DISCREPANCY") or urgency in ("overdue", "due_soon"):
            alert_id = f"fdr-{dep.id}-mat"
            if alert_id not in seen_alert_ids:
                seen_alert_ids.add(alert_id)
                raw_items.append(
                    DeadlineItem(
                        alert_id=alert_id,
                        deposit_id=dep.id,
                        reference_no=dep.reference_no,
                        institution_id=dep.institution_id,
                        institution_name=inst_name,
                        institution_code=inst_code,
                        deadline_type=deadline_type,
                        deadline_label=label,
                        deadline_date=effective_mat,
                        days_left=days_left,
                        urgency=urgency,
                        status=dep.status,
                        amount=Decimal(dep.amount),
                        target_role=target_role,
                        is_my_action=is_my_action,
                        url=f"/deposits/{dep.id}",
                    )
                )

        # 2. Evaluate Scrutiny & Discrepancy Deadlines
        if dep.status == "SUBMITTED":
            scrutiny_deadline = dep.issue_date + timedelta(days=15)
            scrutiny_days = (scrutiny_deadline - today).days
            scrutiny_urgency = "overdue" if scrutiny_days < 0 else ("due_soon" if scrutiny_days <= 7 else "upcoming")
            alert_id = f"fdr-{dep.id}-scrutiny"
            if alert_id not in seen_alert_ids:
                seen_alert_ids.add(alert_id)
                raw_items.append(
                    DeadlineItem(
                        alert_id=alert_id,
                        deposit_id=dep.id,
                        reference_no=dep.reference_no,
                        institution_id=dep.institution_id,
                        institution_name=inst_name,
                        institution_code=inst_code,
                        deadline_type="SCRUTINY_PENDING",
                        deadline_label="Verification Task Pending" if actor.role == "REGULATOR_OFFICER" else "Submitted — Under Scrutiny",
                        deadline_date=scrutiny_deadline,
                        days_left=scrutiny_days,
                        urgency=scrutiny_urgency,
                        status=dep.status,
                        amount=Decimal(dep.amount),
                        target_role="REGULATOR_OFFICER",
                        is_my_action=actor.role in ("REGULATOR_OFFICER", "ADMIN"),
                        url=f"/deposits/{dep.id}",
                    )
                )

        elif dep.status == "DISCREPANCY":
            remedy_deadline = dep.issue_date + timedelta(days=21)
            remedy_days = (remedy_deadline - today).days
            remedy_urgency = "overdue" if remedy_days < 0 else ("due_soon" if remedy_days <= 7 else "upcoming")
            alert_id = f"fdr-{dep.id}-discrepancy"
            if alert_id not in seen_alert_ids:
                seen_alert_ids.add(alert_id)
                raw_items.append(
                    DeadlineItem(
                        alert_id=alert_id,
                        deposit_id=dep.id,
                        reference_no=dep.reference_no,
                        institution_id=dep.institution_id,
                        institution_name=inst_name,
                        institution_code=inst_code,
                        deadline_type="SCRUTINY_PENDING",
                        deadline_label="Discrepancy Remediation Required",
                        deadline_date=remedy_deadline,
                        days_left=remedy_days,
                        urgency=remedy_urgency,
                        status=dep.status,
                        amount=Decimal(dep.amount),
                        target_role="INSTITUTION_USER",
                        is_my_action=actor.role in ("INSTITUTION_USER", "ADMIN"),
                        url=f"/deposits/{dep.id}",
                    )
                )

    # 3. Evaluate Pending Release Approvals
    for rel, dep in pending_releases:
        inst = institutions.get(dep.institution_id)
        inst_name = inst.name if inst else f"Institution #{dep.institution_id}"
        inst_code = inst.code if inst else "N/A"
        # Release decision target deadline: 14 days from request
        decision_date = today + timedelta(days=7)
        alert_id = f"release-{rel.id}-approval"
        if alert_id not in seen_alert_ids:
            seen_alert_ids.add(alert_id)
            raw_items.append(
                DeadlineItem(
                    alert_id=alert_id,
                    deposit_id=dep.id,
                    reference_no=dep.reference_no,
                    institution_id=dep.institution_id,
                    institution_name=inst_name,
                    institution_code=inst_code,
                    deadline_type="RELEASE_APPROVAL",
                    deadline_label=f"Release Approval Request #{rel.id}",
                    deadline_date=decision_date,
                    days_left=7,
                    urgency="due_soon",
                    status="RELEASE_REQUESTED",
                    amount=Decimal(dep.amount),
                    target_role="APPROVING_AUTHORITY",
                    is_my_action=actor.role in ("APPROVING_AUTHORITY", "ADMIN"),
                    url=f"/approvals",
                )
            )

    # Global summary counts before filtering
    summary = DeadlineSummary(
        overdue=sum(1 for i in raw_items if i.urgency == "overdue"),
        due_soon=sum(1 for i in raw_items if i.urgency == "due_soon"),
        upcoming=sum(1 for i in raw_items if i.urgency == "upcoming"),
        completed=sum(1 for i in raw_items if i.urgency == "completed"),
        total=len(raw_items),
    )

    # Apply Category Filters
    filtered = raw_items
    if filter_type == "expiring":
        filtered = [i for i in filtered if i.deadline_type in ("MATURITY", "RENEWAL")]
    elif filter_type == "overdue":
        filtered = [i for i in filtered if i.urgency == "overdue"]
    elif filter_type == "pending_actions":
        filtered = [i for i in filtered if i.is_my_action]

    # Apply Threshold Filters
    if threshold == "30":
        filtered = [i for i in filtered if i.days_left <= 30]
    elif threshold == "15":
        filtered = [i for i in filtered if i.days_left <= 15]
    elif threshold == "7":
        filtered = [i for i in filtered if i.days_left <= 7]
    elif threshold == "overdue":
        filtered = [i for i in filtered if i.days_left < 0]

    # Sort priorities: Overdue first (most negative days_left), then due_soon, upcoming, completed
    urgency_order = {"overdue": 0, "due_soon": 1, "upcoming": 2, "completed": 3}
    filtered.sort(key=lambda item: (urgency_order.get(item.urgency, 99), item.days_left))

    return DeadlinesResponse(
        items=filtered[:limit],
        summary=summary,
    )
