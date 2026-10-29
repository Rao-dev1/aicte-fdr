"""FDR TRACE service: Unified FDR Lineage, append-only lifecycle event journal,
hash-chained event integrity verification, and lineage graph traversal.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, Deposit, FDRLifecycleEvent, FDRLineageRelation, Notification, utcnow

RELATION_TYPES = {
    "ORIGINAL",
    "RENEWAL",
    "AUTO_RENEWAL",
    "REPLACEMENT",
    "SUPERSEDED",
    "RELEASED_CLOSED",
}


def _format_timestamp(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_hash(prev_hash: str, deposit_id: int, event_type: str, actor: str, summary: str, details_json: str, timestamp_str: str) -> str:
    raw = f"{prev_hash}|{deposit_id}|{event_type}|{actor}|{summary}|{details_json}|{timestamp_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_lifecycle_event(
    db: Session,
    deposit_id: int,
    event_type: str,
    actor: str,
    summary: str,
    details: Optional[dict[str, Any]] = None,
    actor_role: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> FDRLifecycleEvent:
    """Appends an immutable lifecycle event to the hash-chained journal."""
    details_str = json.dumps(details or {}, sort_keys=True, default=str)
    
    # Get last event for this deposit
    last_event = db.scalars(
        select(FDRLifecycleEvent)
        .where(FDRLifecycleEvent.deposit_id == deposit_id)
        .order_by(FDRLifecycleEvent.id.desc())
    ).first()

    prev_hash = last_event.event_hash if last_event else "GENESIS"
    now_ts = created_at or utcnow()
    event_hash = _compute_hash(prev_hash, deposit_id, event_type, actor, summary, details_str, _format_timestamp(now_ts))

    event = FDRLifecycleEvent(
        deposit_id=deposit_id,
        event_type=event_type,
        actor=actor,
        actor_role=actor_role,
        summary=summary,
        details_json=details_str,
        prev_hash=prev_hash,
        event_hash=event_hash,
        created_at=now_ts,
    )
    db.add(event)
    db.flush()
    _notify_for_event(db, event)
    return event


# Which role should see each kind of change, and a short heading for it.
NOTIFY_ROLE = {
    "CREATED_SUBMITTED": ("REGULATOR_OFFICER", "New FDR submitted"),
    "DOCUMENT_UPLOADED": ("REGULATOR_OFFICER", "Document uploaded"),
    "DOCUMENT_VERSION_ADDED": ("REGULATOR_OFFICER", "New document version"),
    "VERIFICATION_STATUS_CHANGED": ("INSTITUTION_USER", "Verification update"),
    "RENEWAL_REQUESTED": ("APPROVING_AUTHORITY", "Renewal awaiting approval"),
    "RELEASE_REQUESTED": ("APPROVING_AUTHORITY", "Release awaiting approval"),
    "RENEWAL_APPROVED": ("INSTITUTION_USER", "Renewal approved"),
    "RENEWAL_REJECTED": ("INSTITUTION_USER", "Renewal rejected"),
    "RELEASE_APPROVED": ("INSTITUTION_USER", "Release approved"),
    "RELEASE_REJECTED": ("INSTITUTION_USER", "Release rejected"),
}


def _notify_for_event(db: Session, event: FDRLifecycleEvent) -> None:
    """Puts a notification in the inbox of the role that needs to act on or see this change.
    The kind includes the lifecycle event id, so every change gets its own notification."""
    target = NOTIFY_ROLE.get(event.event_type)
    if target is None:
        return
    role, heading = target
    db.add(
        Notification(
            deposit_id=event.deposit_id,
            kind=f"{event.event_type[:20]}:{event.id}",
            role=role,
            message=f"{heading}: {event.summary}",
        )
    )


def verify_timeline_integrity(events: list[FDRLifecycleEvent]) -> dict[str, Any]:
    """Verifies cryptographic hash chain continuity of historical lifecycle events."""
    if not events:
        return {"valid": True, "event_count": 0, "message": "No events recorded"}

    expected_prev = "GENESIS"
    for idx, ev in enumerate(events):
        if ev.prev_hash != expected_prev:
            return {
                "valid": False,
                "event_count": len(events),
                "broken_at_id": ev.id,
                "broken_index": idx,
                "message": f"Hash continuity broken at event #{ev.id} ({ev.event_type})",
            }
        recalculated = _compute_hash(
            ev.prev_hash,
            ev.deposit_id,
            ev.event_type,
            ev.actor,
            ev.summary,
            ev.details_json,
            _format_timestamp(ev.created_at),
        )
        if recalculated != ev.event_hash:
            return {
                "valid": False,
                "event_count": len(events),
                "broken_at_id": ev.id,
                "broken_index": idx,
                "message": f"Tampering detected: Event #{ev.id} payload does not match cryptographic hash",
            }
        expected_prev = ev.event_hash

    return {
        "valid": True,
        "event_count": len(events),
        "message": f"Tamper-check passed: All {len(events)} events cryptographically verified",
    }


def would_cause_cycle(db: Session, source_id: int, target_id: int) -> bool:
    """Checks whether adding an edge source_id -> target_id creates a cycle in the lineage graph."""
    if source_id == target_id:
        return True

    # Traverse all descendants reachable from target_id.
    visited = set()
    queue = deque([target_id])

    while queue:
        curr = queue.popleft()
        if curr == source_id:
            return True
        if curr in visited:
            continue
        visited.add(curr)

        children = db.scalars(
            select(FDRLineageRelation.target_deposit_id).where(FDRLineageRelation.source_deposit_id == curr)
        ).all()
        for child in children:
            if child not in visited:
                queue.append(child)

    return False


def add_lineage_relation(
    db: Session,
    source_id: int,
    target_id: int,
    relation_type: str,
    actor: str,
    metadata: Optional[dict[str, Any]] = None,
    created_at: Optional[datetime] = None,
) -> FDRLineageRelation:
    """Creates a validated lineage relation between two FDR records."""
    if relation_type not in RELATION_TYPES:
        raise ValueError(f"Invalid relation type '{relation_type}'. Allowed: {', '.join(sorted(RELATION_TYPES))}")

    if source_id == target_id:
        raise ValueError("Invalid lineage link: An FDR cannot be linked to itself.")

    source_dep = db.get(Deposit, source_id)
    target_dep = db.get(Deposit, target_id)
    if not source_dep or not target_dep:
        raise ValueError("Both source and destination deposits must exist.")

    # Check for duplicate
    existing = db.scalars(
        select(FDRLineageRelation).where(
            FDRLineageRelation.source_deposit_id == source_id,
            FDRLineageRelation.target_deposit_id == target_id,
            FDRLineageRelation.relation_type == relation_type,
        )
    ).first()
    if existing:
        return existing

    # Check for cycles
    if would_cause_cycle(db, source_id, target_id):
        raise ValueError(
            f"Circular lineage detected: Linking FDR #{source_id} to FDR #{target_id} would create an invalid loop."
        )

    ts = created_at or utcnow()
    meta_str = json.dumps(metadata or {}, sort_keys=True, default=str)
    rel = FDRLineageRelation(
        source_deposit_id=source_id,
        target_deposit_id=target_id,
        relation_type=relation_type,
        metadata_json=meta_str,
        actor=actor,
        created_at=ts,
    )
    db.add(rel)

    # Record lifecycle events
    record_lifecycle_event(
        db,
        source_id,
        "LINEAGE_LINK_OUTGOING",
        actor,
        f"Linked to FDR #{target_id} ({target_dep.reference_no}) as {relation_type}",
        {"target_deposit_id": target_id, "relation_type": relation_type},
        created_at=ts,
    )
    record_lifecycle_event(
        db,
        target_id,
        "LINEAGE_LINK_INCOMING",
        actor,
        f"Linked from predecessor FDR #{source_id} ({source_dep.reference_no}) as {relation_type}",
        {"source_deposit_id": source_id, "relation_type": relation_type},
        created_at=ts,
    )

    return rel


def ensure_legacy_lineage_synced(db: Session, deposit_id: int):
    """Synchronizes legacy Deposit.previous_deposit_id with FDRLineageRelation."""
    dep = db.get(Deposit, deposit_id)
    if not dep or not dep.previous_deposit_id:
        return

    # Check if relation already recorded
    existing = db.scalars(
        select(FDRLineageRelation).where(
            FDRLineageRelation.source_deposit_id == dep.previous_deposit_id,
            FDRLineageRelation.target_deposit_id == dep.id,
        )
    ).first()

    if not existing:
        rel_type = "RENEWAL" if dep.status == "RENEWED" or "renew" in (dep.bank_name or "").lower() else "REPLACEMENT"
        try:
            add_lineage_relation(
                db,
                source_id=dep.previous_deposit_id,
                target_id=dep.id,
                relation_type=rel_type,
                actor="system",
                metadata={"auto_synced": True, "source": "previous_deposit_id"},
            )
        except ValueError:
            pass


def get_fdr_lineage_graph(db: Session, deposit_id: int) -> dict[str, Any]:
    """Traverses all connected predecessor and successor FDRs in the lineage cluster."""
    ensure_legacy_lineage_synced(db, deposit_id)

    # Discover entire weakly-connected cluster using bidirectional BFS
    visited_ids = set()
    queue = deque([deposit_id])

    while queue:
        curr_id = queue.popleft()
        if curr_id in visited_ids:
            continue
        visited_ids.add(curr_id)

        # Check predecessors and successors via FDRLineageRelation
        forward = db.scalars(
            select(FDRLineageRelation.target_deposit_id).where(FDRLineageRelation.source_deposit_id == curr_id)
        ).all()
        backward = db.scalars(
            select(FDRLineageRelation.source_deposit_id).where(FDRLineageRelation.target_deposit_id == curr_id)
        ).all()

        # Check legacy previous_deposit_id
        curr_dep = db.get(Deposit, curr_id)
        if curr_dep and curr_dep.previous_deposit_id:
            backward.append(curr_dep.previous_deposit_id)

        legacy_children = db.scalars(
            select(Deposit.id).where(Deposit.previous_deposit_id == curr_id)
        ).all()
        forward.extend(legacy_children)

        for neighbor in set(forward + backward):
            if neighbor and neighbor not in visited_ids:
                queue.append(neighbor)

    if not visited_ids:
        visited_ids.add(deposit_id)

    # Load all deposits in the cluster
    deposits = db.scalars(select(Deposit).where(Deposit.id.in_(visited_ids))).all()
    dep_map = {d.id: d for d in deposits}

    # Load all lineage relations inside the cluster
    relations = db.scalars(
        select(FDRLineageRelation).where(
            FDRLineageRelation.source_deposit_id.in_(visited_ids),
            FDRLineageRelation.target_deposit_id.in_(visited_ids),
        )
    ).all()

    # Build node models
    nodes = []
    has_incoming = set()
    for d in deposits:
        nodes.append({
            "id": d.id,
            "reference_no": d.reference_no,
            "bank_name": d.bank_name,
            "amount": float(d.amount),
            "status": d.status,
            "issue_date": str(d.issue_date),
            "maturity_date": str(d.maturity_date),
            "effective_maturity": str(d.effective_maturity),
            "is_current": (d.id == deposit_id),
            "institution_id": d.institution_id,
        })

    edges = []
    seen_edges = set()
    for r in relations:
        key = (r.source_deposit_id, r.target_deposit_id, r.relation_type)
        if key not in seen_edges:
            seen_edges.add(key)
            has_incoming.add(r.target_deposit_id)
            meta = {}
            if r.metadata_json:
                try:
                    meta = json.loads(r.metadata_json)
                except Exception:
                    pass
            edges.append({
                "id": r.id,
                "source": r.source_deposit_id,
                "target": r.target_deposit_id,
                "relation_type": r.relation_type,
                "created_at": r.created_at.isoformat(),
                "actor": r.actor,
                "metadata": meta,
            })

    # Also include legacy links if any wasn't captured in relations
    for d in deposits:
        if d.previous_deposit_id and d.previous_deposit_id in dep_map:
            key = (d.previous_deposit_id, d.id, "RENEWAL")
            if key not in seen_edges and (d.previous_deposit_id, d.id, "REPLACEMENT") not in seen_edges:
                has_incoming.add(d.id)
                edges.append({
                    "id": -d.id,  # synthetic id
                    "source": d.previous_deposit_id,
                    "target": d.id,
                    "relation_type": "RENEWAL",
                    "created_at": d.issue_date.isoformat(),
                    "actor": "system",
                    "metadata": {"legacy": True},
                })

    # Root node: node with no incoming edges, or earliest deposit
    roots = [n["id"] for n in nodes if n["id"] not in has_incoming]
    root_id = roots[0] if roots else (min(dep_map.keys()) if dep_map else deposit_id)

    return {
        "deposit_id": deposit_id,
        "root_id": root_id,
        "nodes": sorted(nodes, key=lambda n: n["issue_date"]),
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


def get_fdr_timeline(db: Session, deposit_id: int) -> dict[str, Any]:
    """Compiles the chronological timeline of events for an FDR from both FDRLifecycleEvent
    and existing AuditLog entries, along with cryptographic integrity check."""
    events = db.scalars(
        select(FDRLifecycleEvent)
        .where(FDRLifecycleEvent.deposit_id == deposit_id)
        .order_by(FDRLifecycleEvent.created_at.asc(), FDRLifecycleEvent.id.asc())
    ).all()

    integrity = verify_timeline_integrity(events)

    timeline_items = []
    # Add structured lifecycle events
    for ev in events:
        details = {}
        if ev.details_json:
            try:
                details = json.loads(ev.details_json)
            except Exception:
                pass
        timeline_items.append({
            "id": f"evt-{ev.id}",
            "source": "LIFECYCLE_JOURNAL",
            "event_type": ev.event_type,
            "actor": ev.actor,
            "actor_role": ev.actor_role,
            "summary": ev.summary,
            "details": details,
            "created_at": ev.created_at.isoformat(),
            "event_hash": ev.event_hash,
            "prev_hash": ev.prev_hash,
        })

    # Also augment with any legacy audit logs for this deposit
    legacy_audits = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity == "deposit", AuditLog.entity_id == deposit_id)
        .order_by(AuditLog.at.asc())
    ).all()

    for al in legacy_audits:
        timeline_items.append({
            "id": f"audit-{al.id}",
            "source": "AUDIT_LOG",
            "event_type": al.action,
            "actor": al.actor,
            "actor_role": None,
            "summary": f"{al.action.replace('_', ' ').title()}",
            "details": {"detail": al.detail},
            "created_at": al.at.isoformat(),
            "event_hash": None,
            "prev_hash": None,
        })

    # Sort all chronologically
    timeline_items.sort(key=lambda item: item["created_at"])

    return {
        "deposit_id": deposit_id,
        "integrity": integrity,
        "events": timeline_items,
        "total_events": len(timeline_items),
    }
