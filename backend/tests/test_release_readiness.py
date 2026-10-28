"""Tests for Feature 2: Release Readiness Graph."""

from datetime import date, timedelta
import pytest
from app.models import Deposit, Document, IntegrityFinding, ReleaseRequest
from app.services import readiness_service
from tests.helpers import create_deposit_payload


def test_missing_document_blocks_readiness(client, auth_headers, db):
    # Create deposit with no documents attached
    p = create_deposit_payload(1, "FDR-READY-MISSING-DOC", amount=500000)
    r = client.post("/api/deposits", json=p, headers=auth_headers)
    dep_id = r.json()["id"]

    res = client.get(f"/api/deposits/{dep_id}/readiness", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["is_ready_for_decision"] is False
    assert data["overall_status"] in ["BLOCKED", "INCOMPLETE"]
    doc_node = next(n for n in data["nodes"] if n["id"] == "PREREQ_DOCUMENTS_ATTACHED")
    assert doc_node["status"] == "MISSING"


def test_unverified_document_does_not_count_as_verified(client, auth_headers, db):
    p = create_deposit_payload(1, "FDR-READY-UNVERIFIED", amount=500000)
    r = client.post("/api/deposits", json=p, headers=auth_headers)
    dep_id = r.json()["id"]

    # Upload document
    doc = Document(
        deposit_id=dep_id,
        filename="fdr_copy.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key_1",
        uploaded_by="inst_user",
    )
    db.add(doc)
    db.commit()

    # FDR is still in SUBMITTED status (unverified by officer)
    res = client.get(f"/api/deposits/{dep_id}/readiness", headers=auth_headers)
    data = res.json()

    doc_node = next(n for n in data["nodes"] if n["id"] == "PREREQ_DOCUMENTS_ATTACHED")
    assert doc_node["status"] == "SATISFIED"

    verify_node = next(n for n in data["nodes"] if n["id"] == "PREREQ_DOCUMENT_VERIFICATION")
    # File exists, but regulatory verification has not occurred!
    assert verify_node["status"] == "REQUIRES_REVIEW"
    assert data["is_ready_for_decision"] is False


def test_high_completion_cannot_bypass_mandatory_blocker(client, auth_headers, officer_headers, db):
    # Deposit that is verified, has docs, but is NOT yet matured (e.g. maturing 3 years from now)
    p = create_deposit_payload(1, "FDR-READY-FUTURE-MAT", amount=500000, issue_date="2025-01-01", maturity_date="2028-01-01")
    r = client.post("/api/deposits", json=p, headers=auth_headers)
    dep_id = r.json()["id"]

    # Attach document
    db.add(Document(
        deposit_id=dep_id,
        filename="fdr_doc.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key_2",
        uploaded_by="inst_user",
    ))
    db.commit()

    # Officer verifies
    v_res = client.post(
        f"/api/deposits/{dep_id}/verify",
        json={
            "confirmed_reference_no": "FDR-READY-FUTURE-MAT",
            "confirmed_bank_name": "State Bank of India",
            "confirmed_amount": 500000,
            "confirmed_issue_date": "2025-01-01",
            "confirmed_maturity_date": "2028-01-01",
            "observations": "Verified perfectly",
        },
        headers=officer_headers,
    )
    assert v_res.status_code == 200

    # Mark deposit as ACTIVE (eligible for release request)
    dep = db.get(Deposit, dep_id)
    dep.status = "ACTIVE"
    db.commit()

    # Submit release request
    rel_res = client.post(f"/api/deposits/{dep_id}/release", headers=auth_headers)
    assert rel_res.status_code == 201

    # Check readiness
    res = client.get(f"/api/deposits/{dep_id}/readiness", headers=auth_headers)
    data = res.json()

    # Completion percentage is high (several nodes satisfied)
    assert data["completion_percentage"] > 50
    # BUT overall status MUST remain BLOCKED due to premature maturity!
    assert data["overall_status"] == "BLOCKED"
    assert data["is_ready_for_decision"] is False
    assert any("maturity" in reason.lower() for reason in data["blocking_reasons"])
