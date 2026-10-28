"""API endpoints for:
1. FDR TRACE (Lineage and Lifecycle Journal)
2. Release Readiness Graph
3. Regulation-Version Replay
4. Cross-Record Integrity Network
"""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .auth import Actor, get_actor, require
from .db import get_db
from .models import Deposit, Institution, IntegrityFinding, RegulationRule, ReleaseRequest
from .schemas import (
    FindingActionCreate,
    LineageLinkCreate,
    RegulationRuleCreate,
    RegulationRuleOut,
    ReplayRequest,
)
from .services import (
    integrity_service,
    readiness_service,
    regulation_service,
    trace_service,
)

router = APIRouter(tags=["advanced_features"])


def get_deposit_scoped(db: Session, deposit_id: int, actor: Actor) -> Deposit:
    dep = db.get(Deposit, deposit_id)
    if not dep or (actor.role == "INSTITUTION_USER" and dep.institution_id != actor.institution_id):
        raise HTTPException(status_code=404, detail="Deposit not found")
    return dep


# ==============================================================================
# FEATURE 1: FDR TRACE
# ==============================================================================


@router.get("/deposits/{deposit_id}/trace")
def get_deposit_trace(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Returns the unified lineage graph and append-only lifecycle event timeline
    for an FDR, including cryptographic hash verification of historical integrity.
    """
    dep = get_deposit_scoped(db, deposit_id, actor)
    lineage = trace_service.get_fdr_lineage_graph(db, dep.id)
    timeline = trace_service.get_fdr_timeline(db, dep.id)

    return {
        "deposit_id": dep.id,
        "reference_no": dep.reference_no,
        "lineage": lineage,
        "timeline": timeline,
    }


@router.post("/deposits/{deposit_id}/lineage", status_code=201)
def link_lineage_relation(
    deposit_id: int,
    body: LineageLinkCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Establishes a validated lineage relation between two FDR records with cycle check."""
    dep = get_deposit_scoped(db, deposit_id, actor)
    target_dep = db.get(Deposit, body.target_deposit_id)
    if not target_dep:
        raise HTTPException(status_code=404, detail=f"Target deposit #{body.target_deposit_id} not found")

    try:
        rel = trace_service.add_lineage_relation(
            db=db,
            source_id=dep.id,
            target_id=target_dep.id,
            relation_type=body.relation_type,
            actor=actor.name,
            metadata=body.metadata,
        )
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": rel.id,
        "source_deposit_id": rel.source_deposit_id,
        "target_deposit_id": rel.target_deposit_id,
        "relation_type": rel.relation_type,
        "message": "Lineage relationship recorded successfully",
    }


@router.get("/trace/search")
def search_trace_records(
    q: Optional[str] = None,
    status: Optional[str] = None,
    bank_name: Optional[str] = None,
    relation_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Searches and filters across lineage nodes and lifecycle records."""
    query = select(Deposit)
    if actor.role == "INSTITUTION_USER":
        query = query.where(Deposit.institution_id == actor.institution_id)

    if q:
        term = f"%{q.strip()}%"
        query = query.where(or_(Deposit.reference_no.ilike(term), Deposit.bank_name.ilike(term)))
    if status:
        query = query.where(Deposit.status == status)
    if bank_name:
        query = query.where(Deposit.bank_name.ilike(f"%{bank_name.strip()}%"))

    total = db.scalar(select(Deposit.id).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Deposit.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()

    results = []
    for d in items:
        trace_service.ensure_legacy_lineage_synced(db, d.id)
        has_predecessor = d.previous_deposit_id is not None
        results.append({
            "id": d.id,
            "reference_no": d.reference_no,
            "bank_name": d.bank_name,
            "amount": float(d.amount),
            "status": d.status,
            "issue_date": str(d.issue_date),
            "maturity_date": str(d.maturity_date),
            "institution_id": d.institution_id,
            "has_predecessor": has_predecessor,
            "previous_deposit_id": d.previous_deposit_id,
        })

    return {"items": results, "total": len(results), "page": page, "page_size": page_size}


# ==============================================================================
# FEATURE 2: RELEASE READINESS GRAPH
# ==============================================================================


@router.get("/deposits/{deposit_id}/readiness")
def get_release_readiness_for_deposit(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Evaluates the prerequisite dependency graph for releasing an FDR deposit."""
    dep = get_deposit_scoped(db, deposit_id, actor)
    return readiness_service.evaluate_release_readiness(db, dep.id, save_snapshot=True)


@router.get("/release-requests/{request_id}/readiness")
def get_release_readiness_for_request(
    request_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Evaluates release readiness directly for an existing release request."""
    req = db.get(ReleaseRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Release request not found")

    dep = get_deposit_scoped(db, req.deposit_id, actor)
    return readiness_service.evaluate_release_readiness(db, dep.id, release_request_id=req.id, save_snapshot=True)


# ==============================================================================
# FEATURE 3: REGULATION-VERSION REPLAY
# ==============================================================================


@router.get("/regulations/rules", response_model=list[RegulationRuleOut])
def list_regulation_rules(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Lists versioned regulation rules."""
    regulation_service.ensure_default_regulations_seeded(db)
    query = select(RegulationRule)
    if status:
        query = query.where(RegulationRule.status == status)
    return db.scalars(query.order_by(RegulationRule.rule_code, RegulationRule.version.desc())).all()


@router.post("/regulations/rules", status_code=201, response_model=RegulationRuleOut)
def create_regulation_rule(
    body: RegulationRuleCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Creates a new regulation rule version."""
    import json

    existing = db.scalars(
        select(RegulationRule).where(
            RegulationRule.rule_code == body.rule_code,
            RegulationRule.version == body.version,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Rule {body.rule_code} v{body.version} already exists")

    rule = RegulationRule(
        rule_code=body.rule_code,
        version=body.version,
        title=body.title,
        description=body.description,
        effective_from=body.effective_from,
        status="DRAFT",
        source_reference=body.source_reference,
        rule_spec_json=json.dumps(body.rule_spec, sort_keys=True),
        change_summary=body.change_summary,
        author=actor.name,
        created_at=trace_service.utcnow(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/regulations/rules/{rule_id}/publish", response_model=RegulationRuleOut)
def publish_regulation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("ADMIN")),
):
    """Publishes a draft rule version and supersedes previous versions with the same rule_code."""
    try:
        rule = regulation_service.publish_rule_version(db, rule_id, author=actor.name)
        db.commit()
        db.refresh(rule)
        return rule
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/regulations/replay")
def replay_regulation_assessment(
    deposit_id: int,
    body: ReplayRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Runs a replay simulation of an FDR's assessment under a target rule version.
    Does not modify or overwrite historical assessment snapshots.
    """
    dep = get_deposit_scoped(db, deposit_id, actor)
    try:
        result = regulation_service.replay_and_compare(
            db=db,
            deposit_id=dep.id,
            target_rule_id=body.target_rule_id,
            assessed_by=actor.name,
        )
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/regulations/rules/{rule_id}/impact-analysis")
def analyze_rule_impact(
    rule_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Analyzes impact of a regulation rule across all active/open cases."""
    try:
        return regulation_service.analyze_rule_impact_on_open_cases(db, rule_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/regulations/snapshots/{deposit_id}")
def get_deposit_snapshots(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Retrieves all historical compliance snapshots for a given FDR."""
    import json
    from .models import AssessmentSnapshot

    dep = get_deposit_scoped(db, deposit_id, actor)
    snapshots = db.scalars(
        select(AssessmentSnapshot)
        .where(AssessmentSnapshot.deposit_id == dep.id)
        .order_by(AssessmentSnapshot.assessed_at.desc())
    ).all()

    return [
        {
            "id": s.id,
            "rule_code": s.rule_code,
            "rule_version": s.rule_version,
            "assessment_type": s.assessment_type,
            "is_replay": s.is_replay,
            "evaluation_result": s.evaluation_result,
            "conditions": json.loads(s.conditions_evaluated_json),
            "assessed_by": s.assessed_by,
            "assessed_at": s.assessed_at.isoformat(),
        }
        for s in snapshots
    ]


# ==============================================================================
# FEATURE 4: CROSS-RECORD INTEGRITY NETWORK
# ==============================================================================


@router.post("/integrity/scan")
def trigger_integrity_scan(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Executes on-demand multi-record integrity anomaly scan."""
    result = integrity_service.run_integrity_scan(db)
    db.commit()
    return result


@router.get("/integrity/findings")
def list_integrity_findings(
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Retrieves detected cross-record integrity findings with filters."""
    # Institution users only see findings touching their own institution
    inst_id = actor.institution_id if actor.role == "INSTITUTION_USER" else None
    return integrity_service.get_integrity_findings(
        db=db,
        status=status,
        category=category,
        severity=severity,
        institution_id=inst_id,
        limit=limit,
        offset=offset,
    )


@router.get("/integrity/findings/{finding_id}")
def get_integrity_finding_detail(
    finding_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Gets detailed view of a specific integrity finding including action history."""
    import json
    from .models import IntegrityFindingAction

    finding = db.get(IntegrityFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if actor.role == "INSTITUTION_USER":
        insts = json.loads(finding.institution_ids or "[]")
        if actor.institution_id not in insts:
            raise HTTPException(status_code=403, detail="Forbidden")

    actions = db.scalars(
        select(IntegrityFindingAction)
        .where(IntegrityFindingAction.finding_id == finding.id)
        .order_by(IntegrityFindingAction.created_at.asc())
    ).all()

    return {
        "id": finding.id,
        "finding_code": finding.finding_code,
        "category": finding.category,
        "severity": finding.severity,
        "status": finding.status,
        "primary_deposit_id": finding.primary_deposit_id,
        "related_deposit_ids": json.loads(finding.related_deposit_ids or "[]"),
        "institution_ids": json.loads(finding.institution_ids or "[]"),
        "explanation": finding.explanation,
        "trigger_values": json.loads(finding.trigger_values_json or "{}"),
        "evidence": json.loads(finding.evidence_json or "{}"),
        "assignee": finding.assignee,
        "first_detected_at": finding.first_detected_at.isoformat(),
        "last_detected_at": finding.last_detected_at.isoformat(),
        "resolved_at": finding.resolved_at.isoformat() if finding.resolved_at else None,
        "resolved_by": finding.resolved_by,
        "resolution_remarks": finding.resolution_remarks,
        "actions": [
            {
                "id": a.id,
                "action": a.action,
                "actor": a.actor,
                "actor_role": a.actor_role,
                "notes": a.notes,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
    }


@router.post("/integrity/findings/{finding_id}/actions")
def act_on_integrity_finding(
    finding_id: int,
    body: FindingActionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "ADMIN")),
):
    """Records an investigation action (comment, assign, status update, false positive, resolve)."""
    try:
        updated = integrity_service.record_finding_action(
            db=db,
            finding_id=finding_id,
            action=body.action,
            actor=actor.name,
            actor_role=actor.role,
            notes=body.notes,
            new_status=body.new_status,
            assignee=body.assignee,
        )
        db.commit()
        return {
            "id": updated.id,
            "status": updated.status,
            "assignee": updated.assignee,
            "message": f"Action '{body.action}' recorded successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/integrity/network")
def get_integrity_network(
    finding_id: Optional[int] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Returns nodes and edges for the cross-record integrity network explorer."""
    inst_id = actor.institution_id if actor.role == "INSTITUTION_USER" else None
    return integrity_service.get_integrity_network_graph(db, finding_id=finding_id, institution_id=inst_id)
