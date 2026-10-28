"""Release Readiness Graph service: Explainable prerequisite dependency graph,
evaluations with concrete evidence, blocker detection, and role-based action recommendations.
"""

from datetime import date
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Deposit,
    Document,
    FDRLifecycleEvent,
    IntegrityFinding,
    ReleaseReadinessEvaluation,
    ReleaseRequest,
    utcnow,
)
from ..scheduler import today_ist


def evaluate_release_readiness(
    db: Session,
    deposit_id: int,
    release_request_id: Optional[int] = None,
    save_snapshot: bool = True,
) -> dict[str, Any]:
    """Evaluates the full prerequisite dependency graph for releasing an FDR deposit.
    Explains exactly why a release is blocked or pending, and provides actionable guidance.
    """
    deposit = db.get(Deposit, deposit_id)
    if not deposit:
        raise ValueError(f"Deposit #{deposit_id} not found")

    rel_req = None
    if release_request_id:
        rel_req = db.get(ReleaseRequest, release_request_id)
    else:
        rel_req = db.scalars(
            select(ReleaseRequest)
            .where(ReleaseRequest.deposit_id == deposit_id)
            .order_by(ReleaseRequest.id.desc())
        ).first()

    today = today_ist()
    docs = db.scalars(select(Document).where(Document.deposit_id == deposit_id)).all()

    # Check for active integrity findings
    open_findings = db.scalars(
        select(IntegrityFinding).where(
            IntegrityFinding.primary_deposit_id == deposit_id,
            IntegrityFinding.status.in_(["OPEN", "UNDER_REVIEW", "CONFIRMED_INCONSISTENCY"]),
            IntegrityFinding.severity.in_(["CRITICAL", "HIGH"]),
        )
    ).all()

    # Define the prerequisite nodes
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    # Node 1: Formal Release Request
    if rel_req:
        n1_status = "SATISFIED"
        n1_reason = f"Release request #{rel_req.id} submitted by {rel_req.requested_by}."
        n1_evidence = {"request_id": rel_req.id, "requested_by": rel_req.requested_by, "remarks": rel_req.remarks}
        n1_action = "Request registered. Proceed to scrutiny."
    else:
        n1_status = "MISSING"
        n1_reason = "No formal release request has been submitted by the institution."
        n1_evidence = {}
        n1_action = "Institution must submit a formal release request with supporting justification."

    nodes.append({
        "id": "PREREQ_APPLICATION_SUBMITTED",
        "category": "APPLICATION",
        "title": "Formal Release Application",
        "is_mandatory": True,
        "status": n1_status,
        "explanation": n1_reason,
        "evidence": n1_evidence,
        "responsible_role": "INSTITUTION_USER",
        "next_action": n1_action,
    })

    # Node 2: Supporting Documentation Attached
    if len(docs) > 0:
        n2_status = "SATISFIED"
        n2_reason = f"{len(docs)} document(s) uploaded ({', '.join(d.filename for d in docs[:3])})."
        n2_evidence = {"document_count": len(docs), "filenames": [d.filename for d in docs]}
        n2_action = "Documents available for verification."
    else:
        n2_status = "MISSING"
        n2_reason = "Required FDR certificate and supporting documents are missing."
        n2_evidence = {"document_count": 0}
        n2_action = "Upload original FDR certificate copy and institution release resolution."

    nodes.append({
        "id": "PREREQ_DOCUMENTS_ATTACHED",
        "category": "DOCUMENTATION",
        "title": "FDR & Supporting Documentation",
        "is_mandatory": True,
        "status": n2_status,
        "explanation": n2_reason,
        "evidence": n2_evidence,
        "responsible_role": "INSTITUTION_USER",
        "next_action": n2_action,
    })

    # Node 3: Identity & Bank Record Consistency
    mismatches = [f for f in (deposit.mismatch_fields or "").split(",") if f.strip()]
    if deposit.status == "DISCREPANCY" or (mismatches and deposit.status != "VERIFIED"):
        n3_status = "BLOCKED"
        n3_reason = f"FDR record has unresolved data discrepancies: {', '.join(mismatches)}."
        n3_evidence = {"mismatches": mismatches, "confirmed_ref": deposit.confirmed_reference_no, "confirmed_bank": deposit.confirmed_bank_name}
        n3_action = "Officer and institution must resolve bank data mismatches or record verified correction."
    elif deposit.status in ["VERIFIED", "ACTIVE", "EXPIRING", "MATURED", "RELEASE_REQUESTED"]:
        n3_status = "SATISFIED"
        n3_reason = f"FDR details match bank confirmation records without discrepancies (Ref: {deposit.reference_no})."
        n3_evidence = {"reference_no": deposit.reference_no, "bank_name": deposit.bank_name, "status": deposit.status}
        n3_action = "FDR identity integrity verified."
    else:
        n3_status = "PENDING"
        n3_reason = f"FDR is in '{deposit.status}' status and requires bank confirmation verification."
        n3_evidence = {"status": deposit.status}
        n3_action = "Regulator officer must complete verification against bank confirmation records."

    nodes.append({
        "id": "PREREQ_IDENTITY_CONSISTENCY",
        "category": "IDENTITY",
        "title": "FDR Identity & Bank Consistency",
        "is_mandatory": True,
        "status": n3_status,
        "explanation": n3_reason,
        "evidence": n3_evidence,
        "responsible_role": "REGULATOR_OFFICER",
        "next_action": n3_action,
    })

    # Node 4: Document Verification State (Do not mark satisfied merely because file exists!)
    if n2_status == "MISSING":
        n4_status = "BLOCKED"
        n4_reason = "Cannot verify documents because no files have been uploaded."
        n4_evidence = {}
        n4_action = "Upload required documentation first."
    elif deposit.status in ["VERIFIED", "ACTIVE", "EXPIRING", "MATURED", "RELEASE_REQUESTED"]:
        n4_status = "SATISFIED"
        n4_reason = "Uploaded documents have been scrutinized and validated against deposit parameters."
        n4_evidence = {"verified": True, "deposit_status": deposit.status}
        n4_action = "Document verification complete."
    else:
        n4_status = "REQUIRES_REVIEW"
        n4_reason = "Documents are uploaded but have not yet undergone regulatory officer verification."
        n4_evidence = {"files_present": len(docs), "verification_pending": True}
        n4_action = "Regulatory officer must complete document scrutiny and mark verified."

    nodes.append({
        "id": "PREREQ_DOCUMENT_VERIFICATION",
        "category": "DOCUMENTATION",
        "title": "Document Verification Status",
        "is_mandatory": True,
        "status": n4_status,
        "explanation": n4_reason,
        "evidence": n4_evidence,
        "responsible_role": "REGULATOR_OFFICER",
        "next_action": n4_action,
    })

    # Node 5: Maturity and Term Eligibility
    eff_mat = deposit.effective_maturity
    days_to_mat = (eff_mat - today).days
    if days_to_mat <= 0:
        n5_status = "SATISFIED"
        n5_reason = f"Maturity date ({eff_mat}) has been reached ({abs(days_to_mat)} days ago)."
        n5_evidence = {"effective_maturity": str(eff_mat), "days_past": abs(days_to_mat)}
        n5_action = "Eligible for release from maturity timing perspective."
    else:
        # Check if an explicit early-release exemption was noted in release request
        has_exemption = rel_req and any(k in (rel_req.remarks or "").lower() for k in ["early release", "exemption", "special approval", "closure order"])
        if has_exemption:
            n5_status = "REQUIRES_REVIEW"
            n5_reason = f"Maturity date is {eff_mat} ({days_to_mat} days remaining). Early release exemption requested."
            n5_evidence = {"effective_maturity": str(eff_mat), "days_remaining": days_to_mat, "exemption_claimed": True}
            n5_action = "Approving authority must specifically inspect and approve early release grounds."
        else:
            n5_status = "BLOCKED"
            n5_reason = f"FDR term is not complete. Maturity date is {eff_mat} ({days_to_mat} days remaining). Normal release requires maturity."
            n5_evidence = {"effective_maturity": str(eff_mat), "days_remaining": days_to_mat}
            n5_action = "Wait until maturity date or obtain authorized early-release clearance."

    nodes.append({
        "id": "PREREQ_MATURITY_ELIGIBILITY",
        "category": "ELIGIBILITY",
        "title": "Maturity & Term Completion",
        "is_mandatory": True,
        "status": n5_status,
        "explanation": n5_reason,
        "evidence": n5_evidence,
        "responsible_role": "REGULATOR_OFFICER",
        "next_action": n5_action,
    })

    # Node 6: Regulatory Integrity & Compliance Checks
    if open_findings:
        crit_count = sum(1 for f in open_findings if f.severity == "CRITICAL")
        n6_status = "BLOCKED"
        n6_reason = f"Blocked by {len(open_findings)} unresolved integrity anomaly ({crit_count} Critical). Issues: {', '.join(f.category for f in open_findings[:2])}."
        n6_evidence = {"finding_ids": [f.id for f in open_findings], "categories": [f.category for f in open_findings]}
        n6_action = "Integrity reviewer must investigate and resolve open integrity findings before release."
    else:
        n6_status = "SATISFIED"
        n6_reason = "No unresolved critical or high-severity integrity findings recorded."
        n6_evidence = {"active_anomalies": 0}
        n6_action = "Compliance integrity check satisfied."

    nodes.append({
        "id": "PREREQ_INTEGRITY_COMPLIANCE",
        "category": "COMPLIANCE",
        "title": "Cross-Record Integrity & Compliance",
        "is_mandatory": True,
        "status": n6_status,
        "explanation": n6_reason,
        "evidence": n6_evidence,
        "responsible_role": "REGULATOR_OFFICER",
        "next_action": n6_action,
    })

    # Node 7: Authorized Scrutiny & Approval Readiness
    if rel_req and rel_req.status == "APPROVED":
        n7_status = "SATISFIED"
        n7_reason = f"Release request already approved by {rel_req.decided_by or 'authority'}."
        n7_evidence = {"status": rel_req.status, "decided_by": rel_req.decided_by}
        n7_action = "Release authorized. Execute closure with bank."
    elif rel_req and rel_req.status == "REJECTED":
        n7_status = "BLOCKED"
        n7_reason = f"Release request was rejected by {rel_req.decided_by or 'authority'}. Reason: {rel_req.remarks}."
        n7_evidence = {"status": rel_req.status, "remarks": rel_req.remarks}
        n7_action = "Institution must submit revised application addressing rejection remarks."
    else:
        # Check if predecessor nodes are satisfied
        all_prior_satisfied = all(
            n["status"] == "SATISFIED"
            for n in nodes
            if n["id"] != "PREREQ_AUTHORITY_APPROVAL"
        )
        if all_prior_satisfied:
            n7_status = "PENDING"
            n7_reason = "All mandatory prerequisites are met. Pending final review by Approving Authority."
            n7_evidence = {"ready_for_review": True}
            n7_action = "Approving Authority may review dossier and record final approval decision."
        else:
            n7_status = "BLOCKED"
            n7_reason = "Cannot submit for final approval until all blocking prerequisite conditions are satisfied."
            n7_evidence = {"prior_conditions_met": False}
            n7_action = "Resolve blocking prerequisites listed above."

    nodes.append({
        "id": "PREREQ_AUTHORITY_APPROVAL",
        "category": "APPROVAL",
        "title": "Approving Authority Decision",
        "is_mandatory": True,
        "status": n7_status,
        "explanation": n7_reason,
        "evidence": n7_evidence,
        "responsible_role": "APPROVING_AUTHORITY",
        "next_action": n7_action,
    })

    # Define Directed Dependency Edges
    edges = [
        {"source": "PREREQ_DOCUMENTS_ATTACHED", "target": "PREREQ_DOCUMENT_VERIFICATION"},
        {"source": "PREREQ_DOCUMENT_VERIFICATION", "target": "PREREQ_IDENTITY_CONSISTENCY"},
        {"source": "PREREQ_APPLICATION_SUBMITTED", "target": "PREREQ_AUTHORITY_APPROVAL"},
        {"source": "PREREQ_IDENTITY_CONSISTENCY", "target": "PREREQ_AUTHORITY_APPROVAL"},
        {"source": "PREREQ_MATURITY_ELIGIBILITY", "target": "PREREQ_AUTHORITY_APPROVAL"},
        {"source": "PREREQ_INTEGRITY_COMPLIANCE", "target": "PREREQ_AUTHORITY_APPROVAL"},
    ]

    # Calculate overall metrics
    satisfied_count = sum(1 for n in nodes if n["status"] == "SATISFIED")
    blocked_count = sum(1 for n in nodes if n["status"] == "BLOCKED")
    missing_count = sum(1 for n in nodes if n["status"] == "MISSING")
    pending_count = sum(1 for n in nodes if n["status"] in ["PENDING", "REQUIRES_REVIEW"])
    total_count = len(nodes)

    # Calculate completion percentage
    # Explicit rule: High completion percentage must never override an unmet mandatory prerequisite!
    completion_percentage = int((satisfied_count / total_count) * 100) if total_count else 0

    blocking_reasons = [
        f"{n['title']}: {n['explanation']}"
        for n in nodes
        if n["status"] in ["BLOCKED", "MISSING"] and n["is_mandatory"]
    ]

    next_actions = [
        {"node": n["title"], "role": n["responsible_role"], "action": n["next_action"]}
        for n in nodes
        if n["status"] != "SATISFIED" and n["is_mandatory"]
    ]

    if blocked_count > 0:
        overall_status = "BLOCKED"
        is_ready = False
    elif missing_count > 0:
        overall_status = "INCOMPLETE"
        is_ready = False
    elif pending_count > 0:
        # Check if only the final authority decision itself is pending
        non_final_pending = [
            n for n in nodes
            if n["id"] != "PREREQ_AUTHORITY_APPROVAL" and n["status"] in ["PENDING", "REQUIRES_REVIEW"]
        ]
        if not non_final_pending:
            overall_status = "READY_FOR_APPROVAL"
            is_ready = True
        else:
            overall_status = "UNDER_REVIEW"
            is_ready = False
    else:
        overall_status = "READY_FOR_APPROVAL"
        is_ready = True

    result = {
        "deposit_id": deposit_id,
        "release_request_id": rel_req.id if rel_req else None,
        "overall_status": overall_status,
        "is_ready_for_decision": is_ready,
        "completion_percentage": completion_percentage,
        "total_prerequisites": total_count,
        "satisfied_count": satisfied_count,
        "blocked_count": blocked_count,
        "missing_count": missing_count,
        "pending_count": pending_count,
        "blocking_reasons": blocking_reasons,
        "next_actions": next_actions,
        "nodes": nodes,
        "edges": edges,
        "evaluated_at": utcnow().isoformat(),
    }

    if save_snapshot:
        db.add(ReleaseReadinessEvaluation(
            deposit_id=deposit_id,
            release_request_id=rel_req.id if rel_req else None,
            overall_status=overall_status,
            total_prerequisites=total_count,
            satisfied_count=satisfied_count,
            blocked_count=blocked_count,
            pending_count=pending_count,
            graph_data_json=json.dumps(result, default=str),
            evaluated_at=utcnow(),
        ))

    return result
