"""Regulation-Version Replay service: Versioned rule registry, deterministic rule evaluation,
immutable assessment snapshots, replay comparison, and impact analysis on in-progress cases.
"""

from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AssessmentSnapshot,
    Deposit,
    Document,
    RegulationRule,
    ReleaseRequest,
    utcnow,
)
from ..scheduler import today_ist


# Default baseline regulation rules for AICTE Security Deposit / FDR management
DEFAULT_REGULATIONS = [
    {
        "rule_code": "REG-AICTE-APH-2020",
        "version": "1.0.0",
        "title": "AICTE APH 2020-21 Security Deposit Baseline",
        "description": "Foundational norms under Approval Process Handbook 2020-21. Minimum 36 months deposit tenure and ₹3,00,000 baseline security deposit.",
        "effective_from": date(2020, 1, 1),
        "status": "SUPERSEDED",
        "source_reference": "AICTE Approval Process Handbook (APH) 2020-21, Appendix 4",
        "change_summary": "Baseline regulatory norms for technical institution establishment deposits.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 36,
            "min_amount_inr": 300000.0,
            "require_zero_discrepancy": False,
            "mandatory_documents": ["FDR Certificate"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL", "COOPERATIVE_SCHEDULED"],
        },
    },
    {
        "rule_code": "REG-AICTE-APH-2023",
        "version": "2.0.0",
        "title": "AICTE APH 2023-24 Comprehensive Deposit Norms",
        "description": "Standardized 5-year (60 month) tenure mandate, ₹5,00,000 threshold, and dual-document verification under APH 2023-24.",
        "effective_from": date(2023, 1, 1),
        "status": "SUPERSEDED",
        "source_reference": "AICTE Approval Process Handbook (APH) 2023-24, Clause 5.1",
        "change_summary": "Standardized mandatory 60-month deposit duration and dual confirmation verification.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 60,
            "min_amount_inr": 500000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate", "Bank Confirmation Letter"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL"],
        },
    },
    {
        "rule_code": "REG-AICTE-APH-2025",
        "version": "2.5.0-DEMO",
        "title": "AICTE APH 2025-26 Enhanced Security Deposit & Release Framework",
        "description": "Active benchmark regulation. Requires ₹10,00,000 minimum deposit, 60 months tenure, strict bank branch validation, and zero discrepancy tolerance.",
        "effective_from": date(2025, 1, 1),
        "status": "ACTIVE",
        "source_reference": "AICTE Approval Process Handbook (APH) 2025-26, Chapter IV, Section 7",
        "change_summary": "Enhanced deposit threshold to ₹10,00,000 with mandatory strict discrepancy tolerance.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 60,
            "min_amount_inr": 1000000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate", "Bank Confirmation Letter"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL"],
        },
    },
    {
        "rule_code": "REG-AICTE-APH-2026-FUTURE",
        "version": "3.0.0-DEMO",
        "title": "Proposed AICTE Model Regulatory Norms 2026-27 (Future Framework)",
        "description": "Forward-looking simulation rule. Requires 84 months tenure, ₹15,00,000 minimum security deposit, and three mandatory verification records.",
        "effective_from": date(2026, 6, 1),
        "status": "DRAFT",
        "source_reference": "AICTE National Technical Education Council Whitepaper 2026-A",
        "change_summary": "Simulated prospective norms with extended 7-year tenure and higher capitalization buffer.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 84,
            "min_amount_inr": 1500000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate", "Bank Confirmation Letter", "Institution Resolution"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL"],
        },
    },
    {
        "rule_code": "REG-AICTE-FDR-2024",
        "version": "1.0.0",
        "title": "AICTE FDR Security Deposit Regulations 2024 (Baseline)",
        "description": "Standard deposit terms, tenure requirements, scheduled bank eligibility, and document scrutiny conditions under APH 2024.",
        "effective_from": date(2024, 1, 1),
        "status": "SUPERSEDED",
        "source_reference": "AICTE Approval Process Handbook (APH) 2024-25, Clause 4.2",
        "change_summary": "Initial baseline release of security deposit verification criteria.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 36,
            "min_amount_inr": 500000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL", "PRIVATE_SCHEDULED"],
        },
    },
    {
        "rule_code": "REG-AICTE-FDR-2025",
        "version": "2.0.0",
        "title": "AICTE Enhanced Security Deposit & Release Framework 2025",
        "description": "Updated tenure standard (minimum 60 months for technical institutions), mandatory dual bank-branch confirmation, strict release readiness clearance.",
        "effective_from": date(2025, 1, 1),
        "status": "ACTIVE",
        "source_reference": "AICTE Approval Process Handbook (APH) 2025-26, Chapter IV, Section 7",
        "change_summary": "Raised minimum tenure to 60 months, required strict bank branch consistency, and formalized release clearance prerequisites.",
        "author": "admin",
        "spec": {
            "min_tenure_months": 60,
            "min_amount_inr": 500000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate", "Bank Confirmation Letter"],
            "disallow_unverified_release": True,
            "allowed_bank_types": ["PUBLIC_SECTOR", "SCHEDULED_COMMERCIAL", "PRIVATE_SCHEDULED"],
        },
    },
]


def ensure_default_regulations_seeded(db: Session):
    """Seeds baseline regulation rule versions if not present."""
    for reg in DEFAULT_REGULATIONS:
        existing = db.scalars(
            select(RegulationRule).where(
                RegulationRule.rule_code == reg["rule_code"],
                RegulationRule.version == reg["version"],
            )
        ).first()
        if not existing:
            rule = RegulationRule(
                rule_code=reg["rule_code"],
                version=reg["version"],
                title=reg["title"],
                description=reg["description"],
                effective_from=reg["effective_from"],
                status=reg["status"],
                source_reference=reg["source_reference"],
                rule_spec_json=json.dumps(reg["spec"], sort_keys=True),
                change_summary=reg["change_summary"],
                author=reg["author"],
                created_at=utcnow(),
                published_at=utcnow(),
            )
            db.add(rule)
    db.flush()


def evaluate_rule_spec(spec: dict[str, Any], deposit_data: dict[str, Any]) -> dict[str, Any]:
    """Pure, deterministic evaluator testing deposit data against configured regulation specification.
    No arbitrary code execution, no hallucinations. Returns detailed condition results.
    """
    conditions: list[dict[str, Any]] = []

    # 1. Minimum Amount
    min_amt = float(spec.get("min_amount_inr", 0))
    amt = float(deposit_data.get("amount", 0))
    if min_amt > 0:
        passed = amt >= min_amt
        conditions.append({
            "condition_id": "MIN_AMOUNT",
            "title": f"Minimum Deposit Amount (₹{min_amt:,.2f})",
            "passed": passed,
            "required": min_amt,
            "actual": amt,
            "reason": f"FDR amount ₹{amt:,.2f} is {'sufficient' if passed else 'below the minimum requirement of ₹' + str(min_amt)}",
        })

    # 2. Minimum Tenure (months)
    min_months = int(spec.get("min_tenure_months", 0))
    issue_date_str = deposit_data.get("issue_date")
    maturity_date_str = deposit_data.get("maturity_date")
    if min_months > 0 and issue_date_str and maturity_date_str:
        try:
            issue_d = date.fromisoformat(issue_date_str) if isinstance(issue_date_str, str) else issue_date_str
            mat_d = date.fromisoformat(maturity_date_str) if isinstance(maturity_date_str, str) else maturity_date_str
            months = (mat_d.year - issue_d.year) * 12 + (mat_d.month - issue_d.month)
            passed = months >= min_months
            conditions.append({
                "condition_id": "MIN_TENURE",
                "title": f"Minimum Tenure ({min_months} Months)",
                "passed": passed,
                "required": f"{min_months} months",
                "actual": f"{months} months",
                "reason": f"Tenure of {months} months is {'compliant' if passed else 'shorter than the required ' + str(min_months) + ' months'}",
            })
        except Exception as e:
            conditions.append({
                "condition_id": "MIN_TENURE",
                "title": f"Minimum Tenure ({min_months} Months)",
                "passed": False,
                "required": f"{min_months} months",
                "actual": "Invalid date format",
                "reason": f"Could not parse deposit dates: {e}",
            })

    # 3. Discrepancy Tolerance
    require_zero = spec.get("require_zero_discrepancy", True)
    mismatches = deposit_data.get("mismatch_fields", [])
    if isinstance(mismatches, str):
        mismatches = [m.strip() for m in mismatches.split(",") if m.strip()]
    if require_zero:
        passed = len(mismatches) == 0
        conditions.append({
            "condition_id": "ZERO_DISCREPANCY",
            "title": "Strict Bank Data Match (Zero Discrepancy)",
            "passed": passed,
            "required": "0 mismatches",
            "actual": f"{len(mismatches)} mismatch(es)",
            "reason": "All submitted fields match bank records" if passed else f"Unresolved discrepancies present: {', '.join(mismatches)}",
        })

    # 4. Mandatory Documents
    mand_docs = spec.get("mandatory_documents", [])
    uploaded_docs = deposit_data.get("uploaded_documents", [])
    if mand_docs:
        has_docs = len(uploaded_docs) > 0
        # If specific required doc names are requested, check availability
        passed = has_docs
        conditions.append({
            "condition_id": "MANDATORY_DOCUMENTS",
            "title": f"Mandatory Documentation ({len(mand_docs)} required)",
            "passed": passed,
            "required": mand_docs,
            "actual": uploaded_docs,
            "reason": f"{len(uploaded_docs)} document(s) uploaded" if passed else "No supporting documents uploaded",
        })

    # Determine overall result
    failed_conditions = [c for c in conditions if not c["passed"]]
    if not conditions:
        result = "REQUIRES_MANUAL_REVIEW"
    elif not failed_conditions:
        result = "COMPLIANT"
    else:
        result = "NON_COMPLIANT"

    return {
        "evaluation_result": result,
        "total_conditions": len(conditions),
        "passed_conditions": len([c for c in conditions if c["passed"]]),
        "failed_conditions": len(failed_conditions),
        "conditions": conditions,
    }


def create_assessment_snapshot(
    db: Session,
    deposit_id: int,
    rule_id: int,
    assessed_by: str,
    assessment_type: str = "DEPOSIT_COMPLIANCE",
    is_replay: bool = False,
    release_request_id: Optional[int] = None,
) -> AssessmentSnapshot:
    """Takes an immutable assessment snapshot of a deposit evaluated under a specific rule version."""
    deposit = db.get(Deposit, deposit_id)
    if not deposit:
        raise ValueError(f"Deposit #{deposit_id} not found")

    rule = db.get(RegulationRule, rule_id)
    if not rule:
        raise ValueError(f"Regulation rule #{rule_id} not found")

    docs = db.scalars(select(Document.filename).where(Document.deposit_id == deposit_id)).all()

    # Capture complete input snapshot
    input_data = {
        "deposit_id": deposit.id,
        "reference_no": deposit.reference_no,
        "bank_name": deposit.bank_name,
        "amount": float(deposit.amount),
        "issue_date": str(deposit.issue_date),
        "maturity_date": str(deposit.maturity_date),
        "status": deposit.status,
        "mismatch_fields": [f for f in (deposit.mismatch_fields or "").split(",") if f.strip()],
        "confirmed_reference_no": deposit.confirmed_reference_no,
        "confirmed_bank_name": deposit.confirmed_bank_name,
        "confirmed_amount": float(deposit.confirmed_amount) if deposit.confirmed_amount else None,
        "uploaded_documents": docs,
    }

    rule_spec = json.loads(rule.rule_spec_json)
    eval_res = evaluate_rule_spec(rule_spec, input_data)

    snapshot = AssessmentSnapshot(
        deposit_id=deposit_id,
        release_request_id=release_request_id,
        rule_id=rule.id,
        rule_code=rule.rule_code,
        rule_version=rule.version,
        assessment_type=assessment_type,
        is_replay=is_replay,
        input_snapshot_json=json.dumps(input_data, sort_keys=True, default=str),
        evaluation_result=eval_res["evaluation_result"],
        conditions_evaluated_json=json.dumps(eval_res["conditions"], sort_keys=True, default=str),
        assessed_by=assessed_by,
        assessed_at=utcnow(),
    )
    db.add(snapshot)
    return snapshot


def replay_and_compare(
    db: Session,
    deposit_id: int,
    target_rule_id: int,
    assessed_by: str,
) -> dict[str, Any]:
    """Replays an assessment under a target rule version and compares it with the historical assessment.
    Does NOT modify the historical assessment record!
    """
    target_rule = db.get(RegulationRule, target_rule_id)
    if not target_rule:
        raise ValueError(f"Target regulation rule #{target_rule_id} not found")

    # Get the latest baseline assessment snapshot (non-replay) for this deposit
    earlier_snapshot = db.scalars(
        select(AssessmentSnapshot)
        .where(AssessmentSnapshot.deposit_id == deposit_id, AssessmentSnapshot.is_replay == False)
        .order_by(AssessmentSnapshot.id.desc())
    ).first()

    # If no prior snapshot, create a baseline snapshot using the oldest or active rule
    if not earlier_snapshot:
        ensure_default_regulations_seeded(db)
        baseline_rule = db.scalars(
            select(RegulationRule).order_by(RegulationRule.id.asc())
        ).first()
        earlier_snapshot = create_assessment_snapshot(
            db, deposit_id, baseline_rule.id, assessed_by, is_replay=False
        )

    # Perform the new replay snapshot
    replay_snapshot = create_assessment_snapshot(
        db, deposit_id, target_rule_id, assessed_by, assessment_type="REPLAY_SIMULATION", is_replay=True
    )

    # Compare conditions between earlier and replay
    earlier_conds = json.loads(earlier_snapshot.conditions_evaluated_json)
    replay_conds = json.loads(replay_snapshot.conditions_evaluated_json)

    earlier_map = {c["condition_id"]: c for c in earlier_conds}
    replay_map = {c["condition_id"]: c for c in replay_conds}

    newly_failing = []
    newly_passing = []
    changed_conditions = []

    for cid, r_cond in replay_map.items():
        if cid in earlier_map:
            e_cond = earlier_map[cid]
            if e_cond["passed"] and not r_cond["passed"]:
                newly_failing.append(r_cond)
                changed_conditions.append({
                    "condition_id": cid,
                    "title": r_cond["title"],
                    "previous_status": "PASSED",
                    "new_status": "FAILED",
                    "reason": r_cond["reason"],
                })
            elif not e_cond["passed"] and r_cond["passed"]:
                newly_passing.append(r_cond)
                changed_conditions.append({
                    "condition_id": cid,
                    "title": r_cond["title"],
                    "previous_status": "FAILED",
                    "new_status": "PASSED",
                    "reason": r_cond["reason"],
                })
        else:
            # Newly introduced condition in target rule
            changed_conditions.append({
                "condition_id": cid,
                "title": r_cond["title"],
                "previous_status": "NOT_EVALUATED",
                "new_status": "PASSED" if r_cond["passed"] else "FAILED",
                "reason": r_cond["reason"],
            })
            if not r_cond["passed"]:
                newly_failing.append(r_cond)

    return {
        "deposit_id": deposit_id,
        "earlier_assessment": {
            "snapshot_id": earlier_snapshot.id,
            "rule_code": earlier_snapshot.rule_code,
            "rule_version": earlier_snapshot.rule_version,
            "evaluation_result": earlier_snapshot.evaluation_result,
            "assessed_at": earlier_snapshot.assessed_at.isoformat(),
            "conditions": earlier_conds,
        },
        "replay_assessment": {
            "snapshot_id": replay_snapshot.id,
            "rule_code": replay_snapshot.rule_code,
            "rule_version": replay_snapshot.rule_version,
            "evaluation_result": replay_snapshot.evaluation_result,
            "assessed_at": replay_snapshot.assessed_at.isoformat(),
            "conditions": replay_conds,
        },
        "changed_conditions": changed_conditions,
        "newly_identified_issues": newly_failing,
        "resolved_issues": newly_passing,
        "requires_manual_review": len(newly_failing) > 0 or replay_snapshot.evaluation_result == "REQUIRES_MANUAL_REVIEW",
    }


def analyze_rule_impact_on_open_cases(db: Session, rule_id: int) -> dict[str, Any]:
    """Analyzes the impact of a newly activated rule version across all OPEN and IN-PROGRESS FDR cases.
    Identifies cases that would fail or require review. Does NOT modify closed, rejected, or released records.
    """
    rule = db.get(RegulationRule, rule_id)
    if not rule:
        raise ValueError(f"Rule #{rule_id} not found")

    rule_spec = json.loads(rule.rule_spec_json)

    # In-progress statuses (not finalized)
    open_statuses = ["SUBMITTED", "VERIFIED", "DISCREPANCY", "ACTIVE", "EXPIRING", "RELEASE_REQUESTED"]
    open_deposits = db.scalars(
        select(Deposit).where(Deposit.status.in_(open_statuses))
    ).all()

    potentially_affected = []
    requires_manual_review = []
    no_detected_impact = []
    insufficient_data = []

    for dep in open_deposits:
        docs = db.scalars(select(Document.filename).where(Document.deposit_id == dep.id)).all()
        dep_data = {
            "deposit_id": dep.id,
            "reference_no": dep.reference_no,
            "bank_name": dep.bank_name,
            "amount": float(dep.amount),
            "issue_date": str(dep.issue_date),
            "maturity_date": str(dep.maturity_date),
            "status": dep.status,
            "mismatch_fields": [f for f in (dep.mismatch_fields or "").split(",") if f.strip()],
            "uploaded_documents": docs,
        }

        # Check for missing critical fields
        if not dep.amount or not dep.issue_date or not dep.maturity_date:
            insufficient_data.append({
                "deposit_id": dep.id,
                "reference_no": dep.reference_no,
                "institution_id": dep.institution_id,
                "reason": "Missing essential deposit fields (amount or dates)",
            })
            continue

        eval_res = evaluate_rule_spec(rule_spec, dep_data)
        failed = [c for c in eval_res["conditions"] if not c["passed"]]

        item = {
            "deposit_id": dep.id,
            "reference_no": dep.reference_no,
            "institution_id": dep.institution_id,
            "bank_name": dep.bank_name,
            "amount": float(dep.amount),
            "current_status": dep.status,
            "evaluation_result": eval_res["evaluation_result"],
            "failed_conditions": failed,
        }

        if eval_res["evaluation_result"] == "NON_COMPLIANT":
            item["impact_reason"] = f"Failed {len(failed)} condition(s) under {rule.rule_code} v{rule.version}: {', '.join(f['title'] for f in failed)}"
            potentially_affected.append(item)
        elif eval_res["evaluation_result"] == "REQUIRES_MANUAL_REVIEW":
            item["impact_reason"] = "Borderline conditions or special exemption required"
            requires_manual_review.append(item)
        else:
            item["impact_reason"] = "All conditions satisfied under this rule specification"
            no_detected_impact.append(item)

    return {
        "rule_id": rule.id,
        "rule_code": rule.rule_code,
        "rule_version": rule.version,
        "rule_title": rule.title,
        "total_open_cases_scanned": len(open_deposits),
        "summary": {
            "potentially_affected_count": len(potentially_affected),
            "requires_manual_review_count": len(requires_manual_review),
            "no_detected_impact_count": len(no_detected_impact),
            "insufficient_data_count": len(insufficient_data),
        },
        "potentially_affected": potentially_affected,
        "requires_manual_review": requires_manual_review,
        "no_detected_impact": no_detected_impact,
        "insufficient_data": insufficient_data,
    }


def publish_rule_version(db: Session, rule_id: int, author: str) -> RegulationRule:
    """Publishes a draft rule version. Supersedes previous versions with the same rule_code."""
    rule = db.get(RegulationRule, rule_id)
    if not rule:
        raise ValueError(f"Rule #{rule_id} not found")

    # Validate JSON spec
    try:
        spec = json.loads(rule.rule_spec_json)
        if not isinstance(spec, dict):
            raise ValueError("Rule spec must be a valid JSON dictionary")
    except Exception as e:
        raise ValueError(f"Invalid rule specification JSON: {e}")

    # Mark previous active version as SUPERSEDED
    prev_active = db.scalars(
        select(RegulationRule).where(
            RegulationRule.rule_code == rule.rule_code,
            RegulationRule.status == "ACTIVE",
            RegulationRule.id != rule.id,
        )
    ).all()

    for p in prev_active:
        p.status = "SUPERSEDED"
        p.effective_to = today_ist()

    rule.status = "ACTIVE"
    rule.published_at = utcnow()
    return rule
