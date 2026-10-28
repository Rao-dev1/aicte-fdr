"""Tests for Feature 4: Cross-Record Integrity Network."""

from datetime import date
import pytest
from app.models import Deposit, IntegrityFinding
from app.services import integrity_service
from tests.helpers import create_deposit_payload


def test_normalized_duplicate_detection(client, auth_headers, officer_headers, db):
    # Deposit 1: "SBI/DELHI/2025"
    p1 = create_deposit_payload(1, "SBI/DELHI/2025", amount=1000000)
    r1 = client.post("/api/deposits", json=p1, headers=auth_headers)
    assert r1.status_code == 201

    # Deposit 2: "sbi-delhi 2025" (different formatting, spaces/hyphens)
    p2 = create_deposit_payload(1, "sbi-delhi 2025", amount=1000000)
    r2 = client.post("/api/deposits", json=p2, headers=auth_headers)
    assert r2.status_code == 201

    # Trigger scan
    scan_res = client.post("/api/integrity/scan", headers=officer_headers)
    assert scan_res.status_code == 200

    # Retrieve findings
    findings_res = client.get("/api/integrity/findings", headers=officer_headers)
    assert findings_res.status_code == 200
    findings = findings_res.json()["items"]

    dup_finding = next((f for f in findings if f["category"] in ["NORMALIZED_DUPLICATE", "DUPLICATE_REFERENCE"]), None)
    assert dup_finding is not None
    assert "formatting" in dup_finding["explanation"].lower() or "duplicate" in dup_finding["explanation"].lower()


def test_repeated_scans_do_not_generate_duplicate_rows(client, auth_headers, officer_headers, db):
    # Create conflicting bank deposit
    p = create_deposit_payload(1, "FDR-DEDUP-SCAN", amount=500000)
    r = client.post("/api/deposits", json=p, headers=auth_headers)
    dep_id = r.json()["id"]

    dep = db.get(Deposit, dep_id)
    dep.confirmed_bank_name = "Completely Different Bank Ltd"
    dep.bank_name = "State Bank of India"
    db.commit()

    # Run scan twice
    scan1 = client.post("/api/integrity/scan", headers=officer_headers).json()
    scan2 = client.post("/api/integrity/scan", headers=officer_headers).json()

    # scan2 should update rather than insert duplicate rows
    assert scan2["findings_generated"] == 0

    findings = client.get("/api/integrity/findings", headers=officer_headers).json()["items"]
    matching = [f for f in findings if f["primary_deposit_id"] == dep_id and f["category"] == "INCONSISTENT_BANK_INSTITUTION"]
    assert len(matching) == 1


def test_reviewer_workflow_and_false_positive_audit(client, auth_headers, officer_headers, db):
    # Trigger finding
    p1 = create_deposit_payload(1, "FDR-REV-1")
    p2 = create_deposit_payload(1, "fdr rev 1")
    client.post("/api/deposits", json=p1, headers=auth_headers)
    client.post("/api/deposits", json=p2, headers=auth_headers)
    client.post("/api/integrity/scan", headers=officer_headers)

    findings = client.get("/api/integrity/findings", headers=officer_headers).json()["items"]
    finding = findings[0]
    fid = finding["id"]

    # Assign and mark false positive with recorded justification
    action_res = client.post(
        f"/api/integrity/findings/{fid}/actions",
        json={
            "action": "STATUS_CHANGE",
            "new_status": "FALSE_POSITIVE",
            "notes": "Verified with bank branch manager: legitimate separate branch voucher series.",
            "assignee": "officer1",
        },
        headers=officer_headers,
    )
    assert action_res.status_code == 200

    # Verify detail and action history
    detail_res = client.get(f"/api/integrity/findings/{fid}", headers=officer_headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] == "FALSE_POSITIVE"
    assert detail["assignee"] == "officer1"
    assert len(detail["actions"]) >= 1
    assert "legitimate separate branch" in detail["actions"][-1]["notes"]
