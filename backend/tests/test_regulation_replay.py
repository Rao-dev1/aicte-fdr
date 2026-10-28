"""Tests for Feature 3: Regulation-Version Replay."""

from datetime import date
import pytest
from app.models import Deposit, RegulationRule
from app.services import regulation_service
from tests.helpers import create_deposit_payload


def test_rule_registry_and_versioning(client, admin_headers, officer_headers, db):
    # List default seeded rules
    res = client.get("/api/regulations/rules", headers=officer_headers)
    assert res.status_code == 200
    rules = res.json()
    assert len(rules) >= 2

    # Create a draft new version v2.1.0
    create_payload = {
        "rule_code": "REG-AICTE-FDR-2025",
        "version": "2.1.0",
        "title": "AICTE FDR Regulations 2025 (Revision 1)",
        "description": "Updated tenure requirement to 72 months.",
        "effective_from": "2025-06-01",
        "source_reference": "Council Notification 2025/06",
        "rule_spec": {
            "min_tenure_months": 72,
            "min_amount_inr": 1000000.0,
            "require_zero_discrepancy": True,
            "mandatory_documents": ["FDR Certificate"],
        },
        "change_summary": "Raised minimum tenure to 72 months.",
    }
    c_res = client.post("/api/regulations/rules", json=create_payload, headers=officer_headers)
    assert c_res.status_code == 201
    new_rule_id = c_res.json()["id"]
    assert c_res.json()["status"] == "DRAFT"

    # Publish rule version
    pub_res = client.post(f"/api/regulations/rules/{new_rule_id}/publish", headers=admin_headers)
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "ACTIVE"


def test_replay_comparison_preserves_historical_snapshot(client, auth_headers, officer_headers, db):
    # 36-month deposit (compliant under v1.0.0, non-compliant under v2.0.0 which requires 60 months)
    p = create_deposit_payload(1, "FDR-REPLAY-COMPARE", amount=500000, issue_date="2022-01-01", maturity_date="2025-01-01")
    r = client.post("/api/deposits", json=p, headers=auth_headers)
    dep_id = r.json()["id"]

    # Attach required FDR Certificate
    from app.models import Document
    db.add(Document(
        deposit_id=dep_id,
        filename="FDR_Certificate.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_key="fdr_cert_key_1",
        uploaded_by="institution1",
    ))
    db.commit()

    # Verify rule list to get v1 and v2 IDs
    rules = client.get("/api/regulations/rules", headers=officer_headers).json()
    rule_v1 = next(r for r in rules if r["version"] == "1.0.0")
    rule_v2 = next(r for r in rules if r["version"] == "2.0.0")

    # Baseline assessment under v1
    snap_v1 = regulation_service.create_assessment_snapshot(
        db, dep_id, rule_v1["id"], assessed_by="officer1", is_replay=False
    )
    db.commit()
    assert snap_v1.evaluation_result == "COMPLIANT"

    # Run replay simulation against v2
    replay_res = client.post(
        f"/api/regulations/replay?deposit_id={dep_id}",
        json={"target_rule_id": rule_v2["id"]},
        headers=officer_headers,
    )
    assert replay_res.status_code == 200
    data = replay_res.json()

    # Baseline snapshot must remain untouched
    assert data["earlier_assessment"]["rule_version"] == "1.0.0"
    assert data["earlier_assessment"]["evaluation_result"] == "COMPLIANT"

    # Replay simulation evaluates to NON_COMPLIANT because tenure is 36 months (< 60)
    assert data["replay_assessment"]["rule_version"] == "2.0.0"
    assert data["replay_assessment"]["evaluation_result"] == "NON_COMPLIANT"
    assert len(data["newly_identified_issues"]) >= 1
    assert any("tenure" in i["title"].lower() for i in data["newly_identified_issues"])


def test_impact_analysis_on_open_cases(client, auth_headers, officer_headers, db):
    # Open deposit with 24-month tenure
    p = create_deposit_payload(1, "FDR-IMPACT-TEST", amount=500000, issue_date="2024-01-01", maturity_date="2026-01-01")
    client.post("/api/deposits", json=p, headers=auth_headers)

    rules = client.get("/api/regulations/rules", headers=officer_headers).json()
    rule_v2 = next(r for r in rules if r["version"] == "2.0.0")

    impact_res = client.get(f"/api/regulations/rules/{rule_v2['id']}/impact-analysis", headers=officer_headers)
    assert impact_res.status_code == 200
    data = impact_res.json()

    assert data["total_open_cases_scanned"] >= 1
    assert "summary" in data
    assert any(c["reference_no"] == "FDR-IMPACT-TEST" for c in data["potentially_affected"])
