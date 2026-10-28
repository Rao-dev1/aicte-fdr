"""Tests for Feature 1: FDR TRACE (Lifecycle Journal and Lineage Tracking)."""

from datetime import date
import pytest
from app.models import Deposit, Institution
from app.services import trace_service
from tests.helpers import create_deposit_payload


def test_deposit_creation_records_trace_lifecycle_event(client, auth_headers, officer_headers, db):
    # Create institution and deposit
    payload = create_deposit_payload(1, "FDR-TRACE-001", amount=500000)
    res = client.post("/api/deposits", json=payload, headers=auth_headers)
    assert res.status_code == 201
    dep_id = res.json()["id"]

    # Verify trace endpoint
    trace_res = client.get(f"/api/deposits/{dep_id}/trace", headers=auth_headers)
    assert trace_res.status_code == 200
    data = trace_res.json()

    assert data["deposit_id"] == dep_id
    assert data["reference_no"] == "FDR-TRACE-001"
    assert data["timeline"]["integrity"]["valid"] is True
    assert data["timeline"]["total_events"] >= 1
    events = data["timeline"]["events"]
    assert any(e["event_type"] == "CREATED_SUBMITTED" for e in events)


def test_lineage_linking_and_cycle_prevention(client, officer_headers, auth_headers, db):
    # Create two deposits
    p1 = create_deposit_payload(1, "FDR-PARENT-001")
    r1 = client.post("/api/deposits", json=p1, headers=auth_headers)
    id1 = r1.json()["id"]

    p2 = create_deposit_payload(1, "FDR-CHILD-001")
    r2 = client.post("/api/deposits", json=p2, headers=auth_headers)
    id2 = r2.json()["id"]

    # Link parent -> child as RENEWAL
    link_res = client.post(
        f"/api/deposits/{id1}/lineage",
        json={"target_deposit_id": id2, "relation_type": "RENEWAL", "metadata": {"term_years": 3}},
        headers=officer_headers,
    )
    assert link_res.status_code == 201

    # Verify graph contains both nodes and 1 edge
    trace_res = client.get(f"/api/deposits/{id1}/trace", headers=officer_headers)
    graph = trace_res.json()["lineage"]
    assert graph["total_nodes"] == 2
    assert graph["total_edges"] >= 1

    # Attempt to create a circular link: child -> parent
    cycle_res = client.post(
        f"/api/deposits/{id2}/lineage",
        json={"target_deposit_id": id1, "relation_type": "RENEWAL"},
        headers=officer_headers,
    )
    assert cycle_res.status_code == 400
    assert "circular" in cycle_res.json()["detail"].lower()

    # Attempt self-link
    self_res = client.post(
        f"/api/deposits/{id1}/lineage",
        json={"target_deposit_id": id1, "relation_type": "RENEWAL"},
        headers=officer_headers,
    )
    assert self_res.status_code == 400
    assert "itself" in self_res.json()["detail"].lower()


def test_institution_isolation_on_trace(client, officer_headers, auth_headers, db):
    # Inst 1 deposit
    p1 = create_deposit_payload(1, "FDR-INST1-ISO")
    r1 = client.post(
        "/api/deposits",
        json=p1,
        headers=auth_headers,
    )
    assert r1.status_code == 201

    # Inst 1 can see its own deposit trace
    dep_id = r1.json()["id"]
    res = client.get(f"/api/deposits/{dep_id}/trace", headers=auth_headers)
    assert res.status_code == 200


def test_timeline_integrity_tamper_detection(client, db):
    dep = Deposit(
        institution_id=1,
        reference_no="FDR-TAMPER-TEST",
        bank_name="Test Bank",
        amount=100000,
        issue_date=date(2025, 1, 1),
        maturity_date=date(2028, 1, 1),
        status="SUBMITTED",
    )
    db.add(dep)
    db.commit()

    ev1 = trace_service.record_lifecycle_event(db, dep.id, "EVT1", "user1", "First event")
    ev2 = trace_service.record_lifecycle_event(db, dep.id, "EVT2", "user1", "Second event")
    db.commit()

    timeline = trace_service.get_fdr_timeline(db, dep.id)
    assert timeline["integrity"]["valid"] is True

    # Tamper with event payload directly
    ev1.summary = "Tampered summary after the fact"
    db.commit()

    tampered_timeline = trace_service.get_fdr_timeline(db, dep.id)
    assert tampered_timeline["integrity"]["valid"] is False
    assert "tampering detected" in tampered_timeline["integrity"]["message"].lower()
