"""Cross-Record Integrity Network service: Multi-record anomaly detection,
deterministic deduplicated findings, network graph explorer, and reviewer investigation workflow.
"""

from collections import defaultdict
from datetime import datetime
import json
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
    Deposit,
    Document,
    FDRLineageRelation,
    Institution,
    IntegrityFinding,
    IntegrityFindingAction,
    ReleaseRequest,
    utcnow,
)


def _normalize_ref(ref: str) -> str:
    """Normalizes FDR reference number by stripping non-alphanumeric characters and converting to lowercase."""
    return re.sub(r"[^a-zA-Z0-9]", "", ref or "").lower()


def run_integrity_scan(db: Session, institution_id: Optional[int] = None) -> dict[str, Any]:
    """Runs comprehensive cross-record integrity checks across deposits, documents,
    lineage links, and release requests. Deduplicates findings using finding_code.
    """
    query = select(Deposit)
    if institution_id:
        query = query.where(Deposit.institution_id == institution_id)
    deposits = db.scalars(query).all()
    dep_map = {d.id: d for d in deposits}

    findings_generated = 0
    findings_updated = 0

    def record_or_update_finding(
        finding_code: str,
        category: str,
        severity: str,
        explanation: str,
        primary_dep_id: Optional[int],
        related_dep_ids: list[int],
        inst_ids: list[int],
        trigger_values: dict[str, Any],
        evidence: dict[str, Any],
    ):
        nonlocal findings_generated, findings_updated
        existing = db.scalars(
            select(IntegrityFinding).where(IntegrityFinding.finding_code == finding_code)
        ).first()

        now = utcnow()
        if existing:
            # If already marked FALSE_POSITIVE or RESOLVED, respect reviewer verdict
            if existing.status in ["FALSE_POSITIVE", "RESOLVED"]:
                return
            existing.last_detected_at = now
            existing.trigger_values_json = json.dumps(trigger_values, sort_keys=True, default=str)
            existing.evidence_json = json.dumps(evidence, sort_keys=True, default=str)
            findings_updated += 1
        else:
            finding = IntegrityFinding(
                finding_code=finding_code,
                category=category,
                severity=severity,
                status="OPEN",
                primary_deposit_id=primary_dep_id,
                related_deposit_ids=json.dumps(related_dep_ids),
                institution_ids=json.dumps(inst_ids),
                explanation=explanation,
                trigger_values_json=json.dumps(trigger_values, sort_keys=True, default=str),
                evidence_json=json.dumps(evidence, sort_keys=True, default=str),
                first_detected_at=now,
                last_detected_at=now,
            )
            db.add(finding)
            findings_generated += 1

    # --- CHECK 1 & 2: Normalized Duplicate Reference Numbers ---
    norm_groups: dict[str, list[Deposit]] = defaultdict(list)
    for d in deposits:
        norm = _normalize_ref(d.reference_no)
        if norm:
            norm_groups[norm].append(d)

    for norm, group in norm_groups.items():
        if len(group) > 1:
            # Check if they are distinct records
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    d1, d2 = group[i], group[j]
                    is_exact = d1.reference_no.strip() == d2.reference_no.strip()
                    code = f"DUP_REF:{norm}:{min(d1.id, d2.id)}:{max(d1.id, d2.id)}"
                    category = "DUPLICATE_REFERENCE" if is_exact else "NORMALIZED_DUPLICATE"
                    severity = "CRITICAL" if is_exact else "HIGH"
                    expl = (
                        f"Exact duplicate FDR reference number '{d1.reference_no}' detected across deposits #{d1.id} and #{d2.id}."
                        if is_exact
                        else f"Potential duplicate reference numbers due to formatting differences: '{d1.reference_no}' (FDR #{d1.id}) vs '{d2.reference_no}' (FDR #{d2.id})."
                    )
                    record_or_update_finding(
                        finding_code=code,
                        category=category,
                        severity=severity,
                        explanation=expl,
                        primary_dep_id=d1.id,
                        related_dep_ids=[d1.id, d2.id],
                        inst_ids=list({d1.institution_id, d2.institution_id}),
                        trigger_values={"ref1": d1.reference_no, "ref2": d2.reference_no, "normalized": norm},
                        evidence={"d1_amount": float(d1.amount), "d2_amount": float(d2.amount), "d1_bank": d1.bank_name, "d2_bank": d2.bank_name},
                    )

    # --- CHECK 3: Conflicting Amounts or Dates Across Lineage ---
    lineage_rels = db.scalars(select(FDRLineageRelation)).all()
    for rel in lineage_rels:
        s_dep = dep_map.get(rel.source_deposit_id) or db.get(Deposit, rel.source_deposit_id)
        t_dep = dep_map.get(rel.target_deposit_id) or db.get(Deposit, rel.target_deposit_id)
        if s_dep and t_dep:
            # In renewals, new issue date should be around or after predecessor maturity date
            if t_dep.issue_date < s_dep.issue_date:
                code = f"LINEAGE_DATE_CONFLICT:{s_dep.id}:{t_dep.id}"
                record_or_update_finding(
                    finding_code=code,
                    category="AMOUNT_DATE_CONFLICT",
                    severity="HIGH",
                    explanation=f"Successor FDR #{t_dep.id} ({t_dep.reference_no}) has an issue date ({t_dep.issue_date}) preceding ancestor FDR #{s_dep.id} ({s_dep.issue_date}).",
                    primary_dep_id=t_dep.id,
                    related_dep_ids=[s_dep.id, t_dep.id],
                    inst_ids=list({s_dep.institution_id, t_dep.institution_id}),
                    trigger_values={"predecessor_issue": str(s_dep.issue_date), "successor_issue": str(t_dep.issue_date)},
                    evidence={"predecessor_maturity": str(s_dep.maturity_date), "relation_type": rel.relation_type},
                )

    # --- CHECK 4: Inconsistent Bank or Institution Information ---
    for d in deposits:
        if d.confirmed_bank_name and d.bank_name:
            c_bank = d.confirmed_bank_name.strip().lower()
            s_bank = d.bank_name.strip().lower()
            if c_bank != s_bank and not (c_bank in s_bank or s_bank in c_bank):
                code = f"BANK_MISMATCH:{d.id}"
                record_or_update_finding(
                    finding_code=code,
                    category="INCONSISTENT_BANK_INSTITUTION",
                    severity="HIGH",
                    explanation=f"FDR #{d.id} ({d.reference_no}) submitted bank '{d.bank_name}' conflicts with bank-confirmed '{d.confirmed_bank_name}'.",
                    primary_dep_id=d.id,
                    related_dep_ids=[d.id],
                    inst_ids=[d.institution_id],
                    trigger_values={"submitted_bank": d.bank_name, "confirmed_bank": d.confirmed_bank_name},
                    evidence={"mismatch_fields": d.mismatch_fields, "status": d.status},
                )

    # --- CHECK 5 & 10: Replacement / Renewal Predecessor Validation ---
    for d in deposits:
        if d.previous_deposit_id:
            pred = db.get(Deposit, d.previous_deposit_id)
            if not pred:
                code = f"INVALID_PREDECESSOR:{d.id}:{d.previous_deposit_id}"
                record_or_update_finding(
                    finding_code=code,
                    category="INVALID_PREDECESSOR_LINK",
                    severity="CRITICAL",
                    explanation=f"FDR #{d.id} references predecessor FDR #{d.previous_deposit_id} which does not exist in the database.",
                    primary_dep_id=d.id,
                    related_dep_ids=[d.id],
                    inst_ids=[d.institution_id],
                    trigger_values={"missing_predecessor_id": d.previous_deposit_id},
                    evidence={"fdr_status": d.status},
                )
            elif pred.institution_id != d.institution_id:
                code = f"CROSS_INST_PREDECESSOR:{d.id}:{pred.id}"
                record_or_update_finding(
                    finding_code=code,
                    category="INCONSISTENT_BANK_INSTITUTION",
                    severity="CRITICAL",
                    explanation=f"FDR #{d.id} belongs to institution #{d.institution_id} but its predecessor FDR #{pred.id} belongs to another institution #{pred.institution_id}.",
                    primary_dep_id=d.id,
                    related_dep_ids=[d.id, pred.id],
                    inst_ids=[d.institution_id, pred.institution_id],
                    trigger_values={"inst_current": d.institution_id, "inst_predecessor": pred.institution_id},
                    evidence={"current_ref": d.reference_no, "pred_ref": pred.reference_no},
                )

    # --- CHECK 7: Multiple Active Records for Same Underlying Deposit ---
    active_by_inst_amount: dict[tuple[int, float], list[Deposit]] = defaultdict(list)
    for d in deposits:
        if d.status in ["ACTIVE", "EXPIRING"]:
            active_by_inst_amount[(d.institution_id, float(d.amount))].append(d)

    for (inst_id, amt), group in active_by_inst_amount.items():
        if len(group) > 1:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    d1, d2 = group[i], group[j]
                    if d1.bank_name.strip().lower() == d2.bank_name.strip().lower() and abs((d1.maturity_date - d2.maturity_date).days) < 30:
                        code = f"MULTIPLE_ACTIVE_SUSPECT:{min(d1.id, d2.id)}:{max(d1.id, d2.id)}"
                        record_or_update_finding(
                            finding_code=code,
                            category="MULTIPLE_ACTIVE_DEPOSITS",
                            severity="MEDIUM",
                            explanation=f"Multiple active FDRs #{d1.id} ({d1.reference_no}) and #{d2.id} ({d2.reference_no}) share identical bank, amount (₹{amt:,.2f}), and near-identical maturity dates.",
                            primary_dep_id=d1.id,
                            related_dep_ids=[d1.id, d2.id],
                            inst_ids=[inst_id],
                            trigger_values={"amount": amt, "d1_ref": d1.reference_no, "d2_ref": d2.reference_no},
                            evidence={"d1_mat": str(d1.maturity_date), "d2_mat": str(d2.maturity_date)},
                        )

    # --- CHECK 8: Release Requests Linked to Inconsistent / Superseded Records ---
    releases = db.scalars(select(ReleaseRequest)).all()
    for rel in releases:
        dep = db.get(Deposit, rel.deposit_id)
        if dep and dep.status == "RENEWED":
            code = f"RELEASE_ON_SUPERSEDED:{rel.id}:{dep.id}"
            record_or_update_finding(
                finding_code=code,
                category="SUPERSEDED_RELEASE_LINK",
                severity="HIGH",
                explanation=f"Release request #{rel.id} is linked to FDR #{dep.id} ({dep.reference_no}) which has already been superseded by renewal.",
                primary_dep_id=dep.id,
                related_dep_ids=[dep.id],
                inst_ids=[dep.institution_id],
                trigger_values={"release_id": rel.id, "deposit_status": dep.status},
                evidence={"requested_by": rel.requested_by, "remarks": rel.remarks},
            )

    db.flush()
    return {
        "status": "ok",
        "findings_generated": findings_generated,
        "findings_updated": findings_updated,
        "total_active_deposits_checked": len(deposits),
    }


def get_integrity_findings(
    db: Session,
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    institution_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Retrieves filtered integrity findings with summary statistics."""
    query = select(IntegrityFinding)
    if status:
        query = query.where(IntegrityFinding.status == status)
    if category:
        query = query.where(IntegrityFinding.category == category)
    if severity:
        query = query.where(IntegrityFinding.severity == severity)

    all_findings = db.scalars(query.order_by(IntegrityFinding.last_detected_at.desc())).all()

    # Filter by institution if applicable
    if institution_id:
        filtered = []
        for f in all_findings:
            insts = json.loads(f.institution_ids or "[]")
            if institution_id in insts:
                filtered.append(f)
        all_findings = filtered

    total = len(all_findings)
    items = all_findings[offset : offset + limit]

    findings_out = []
    for f in items:
        findings_out.append({
            "id": f.id,
            "finding_code": f.finding_code,
            "category": f.category,
            "severity": f.severity,
            "status": f.status,
            "primary_deposit_id": f.primary_deposit_id,
            "related_deposit_ids": json.loads(f.related_deposit_ids or "[]"),
            "institution_ids": json.loads(f.institution_ids or "[]"),
            "explanation": f.explanation,
            "trigger_values": json.loads(f.trigger_values_json or "{}"),
            "evidence": json.loads(f.evidence_json or "{}"),
            "assignee": f.assignee,
            "first_detected_at": f.first_detected_at.isoformat(),
            "last_detected_at": f.last_detected_at.isoformat(),
            "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
            "resolved_by": f.resolved_by,
            "resolution_remarks": f.resolution_remarks,
        })

    # Summary counts
    counts_by_status = defaultdict(int)
    counts_by_severity = defaultdict(int)
    for f in all_findings:
        counts_by_status[f.status] += 1
        counts_by_severity[f.severity] += 1

    return {
        "items": findings_out,
        "total": total,
        "page": (offset // limit) + 1 if limit else 1,
        "page_size": limit,
        "summary": {
            "by_status": dict(counts_by_status),
            "by_severity": dict(counts_by_severity),
            "open_critical": counts_by_severity.get("CRITICAL", 0),
        },
    }


def record_finding_action(
    db: Session,
    finding_id: int,
    action: str,
    actor: str,
    actor_role: str,
    notes: str = "",
    new_status: Optional[str] = None,
    assignee: Optional[str] = None,
) -> IntegrityFinding:
    """Records an investigation action, status transition, assignment, or review note."""
    finding = db.get(IntegrityFinding, finding_id)
    if not finding:
        raise ValueError(f"Finding #{finding_id} not found")

    old_status = finding.status
    if new_status:
        finding.status = new_status
        if new_status in ["RESOLVED", "FALSE_POSITIVE"]:
            finding.resolved_at = utcnow()
            finding.resolved_by = actor
            finding.resolution_remarks = notes

    if assignee is not None:
        finding.assignee = assignee

    act = IntegrityFindingAction(
        finding_id=finding.id,
        action=action,
        actor=actor,
        actor_role=actor_role,
        notes=notes,
        created_at=utcnow(),
    )
    db.add(act)

    # Record in AuditLog
    db.add(AuditLog(
        entity="integrity_finding",
        entity_id=finding.id,
        action=f"INTEGRITY_{action}",
        actor=actor,
        detail=f"Status: {old_status} -> {finding.status}. Notes: {notes}",
    ))

    return finding


def get_integrity_network_graph(db: Session, finding_id: Optional[int] = None, institution_id: Optional[int] = None) -> dict[str, Any]:
    """Assembles node and edge graph for the visual network explorer."""
    query = select(IntegrityFinding)
    if finding_id:
        query = query.where(IntegrityFinding.id == finding_id)
    findings = db.scalars(query.order_by(IntegrityFinding.last_detected_at.desc()).limit(30)).all()

    dep_ids = set()
    inst_ids = set()
    nodes = []
    edges = []

    for f in findings:
        nodes.append({
            "id": f"find-{f.id}",
            "type": "finding",
            "label": f"{f.category.replace('_', ' ')}",
            "category": f.category,
            "severity": f.severity,
            "status": f.status,
            "explanation": f.explanation,
            "finding_id": f.id,
        })
        r_deps = json.loads(f.related_deposit_ids or "[]")
        dep_ids.update(r_deps)
        if f.primary_deposit_id:
            dep_ids.add(f.primary_deposit_id)
            edges.append({
                "source": f"find-{f.id}",
                "target": f"dep-{f.primary_deposit_id}",
                "relation": "FLAGS",
                "severity": f.severity,
            })
        for r_id in r_deps:
            if r_id != f.primary_deposit_id:
                edges.append({
                    "source": f"find-{f.id}",
                    "target": f"dep-{r_id}",
                    "relation": "COLLIDES_WITH",
                    "severity": f.severity,
                })

    # Fetch deposit nodes
    if dep_ids:
        deposits = db.scalars(select(Deposit).where(Deposit.id.in_(dep_ids))).all()
        for d in deposits:
            inst_ids.add(d.institution_id)
            nodes.append({
                "id": f"dep-{d.id}",
                "type": "deposit",
                "label": f"FDR {d.reference_no}",
                "reference_no": d.reference_no,
                "bank_name": d.bank_name,
                "amount": float(d.amount),
                "status": d.status,
                "deposit_id": d.id,
            })
            # Connect deposit to its institution
            edges.append({
                "source": f"inst-{d.institution_id}",
                "target": f"dep-{d.id}",
                "relation": "OWNS",
                "severity": "NORMAL",
            })

    # Fetch institution nodes
    if inst_ids:
        institutions = db.scalars(select(Institution).where(Institution.id.in_(inst_ids))).all()
        for inst in institutions:
            nodes.append({
                "id": f"inst-{inst.id}",
                "type": "institution",
                "label": inst.name,
                "code": inst.code,
                "institution_id": inst.id,
            })

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }
