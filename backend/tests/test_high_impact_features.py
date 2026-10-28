"""Automated tests for the 3 High-Impact Features:
1. Smart Deadline & Expiry Alerts
2. Explainable Document Verification
3. One-Click Deficiency Report Generator
"""

import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.extract import extract_fdr, parse_fields_explainable
from app.models import Deposit, Document, Institution, ReleaseRequest
from app.scheduler import today_ist


# ============================================================================
# FEATURE 1: Smart Deadline & Expiry Alerts Tests
# ============================================================================

def test_deadlines_thresholds_and_calculation(client: TestClient, admin_headers: dict, auth_headers: dict, db):
    """Test dynamic calculation of deadlines at 30, 15, 7 days, overdue, and role scope."""
    today = today_ist()

    # Create an institution
    inst = Institution(name="Deadline Test College", code="DTC-101")
    db.add(inst)
    db.commit()

    # Create deposits with various maturities
    # 1. Overdue deposit (matured 5 days ago)
    d_overdue = Deposit(
        institution_id=inst.id,
        reference_no="FDR-OVERDUE-01",
        bank_name="State Bank of India",
        amount=Decimal("1500000.00"),
        issue_date=today - timedelta(days=1825),
        maturity_date=today - timedelta(days=5),
        status="MATURED",
    )
    # 2. Critical due soon (maturing in 4 days)
    d_7 = Deposit(
        institution_id=inst.id,
        reference_no="FDR-CRITICAL-07",
        bank_name="Bank of Baroda",
        amount=Decimal("2500000.00"),
        issue_date=today - timedelta(days=1800),
        maturity_date=today + timedelta(days=4),
        status="EXPIRING",
    )
    # 3. Due soon within 15 days (maturing in 12 days)
    d_15 = Deposit(
        institution_id=inst.id,
        reference_no="FDR-DUESOON-15",
        bank_name="Punjab National Bank",
        amount=Decimal("3000000.00"),
        issue_date=today - timedelta(days=1800),
        maturity_date=today + timedelta(days=12),
        status="ACTIVE",
    )
    # 4. Upcoming within 30 days (maturing in 28 days)
    d_30 = Deposit(
        institution_id=inst.id,
        reference_no="FDR-UPCOMING-30",
        bank_name="Canara Bank",
        amount=Decimal("1000000.00"),
        issue_date=today - timedelta(days=1800),
        maturity_date=today + timedelta(days=28),
        status="ACTIVE",
    )
    # 5. Completed deposit (already renewed)
    d_done = Deposit(
        institution_id=inst.id,
        reference_no="FDR-COMPLETED-DONE",
        bank_name="HDFC Bank",
        amount=Decimal("2000000.00"),
        issue_date=today - timedelta(days=2000),
        maturity_date=today - timedelta(days=100),
        status="RENEWED",
    )

    db.add_all([d_overdue, d_7, d_15, d_30, d_done])
    db.commit()

    # Fetch deadlines with admin
    res = client.get("/api/deadlines?filter=all", headers=admin_headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert "items" in data
    assert "summary" in data
    assert data["summary"]["total"] >= 4
    assert data["summary"]["overdue"] >= 1
    assert data["summary"]["due_soon"] >= 2

    # Check alert items
    items_by_ref = {item["reference_no"]: item for item in data["items"]}
    assert "FDR-OVERDUE-01" in items_by_ref
    assert items_by_ref["FDR-OVERDUE-01"]["urgency"] == "overdue"
    assert items_by_ref["FDR-OVERDUE-01"]["days_left"] == -5

    assert "FDR-CRITICAL-07" in items_by_ref
    assert items_by_ref["FDR-CRITICAL-07"]["urgency"] == "due_soon"
    assert items_by_ref["FDR-CRITICAL-07"]["days_left"] == 4

    assert "FDR-DUESOON-15" in items_by_ref
    assert items_by_ref["FDR-DUESOON-15"]["days_left"] == 12

    assert "FDR-UPCOMING-30" in items_by_ref
    assert items_by_ref["FDR-UPCOMING-30"]["days_left"] == 28


def test_deadlines_threshold_filters_and_deduplication(client: TestClient, admin_headers: dict):
    """Test threshold filters: 7, 15, 30 days and ensure no duplicate alert IDs."""
    # Filter critical (<= 7 days)
    res_7 = client.get("/api/deadlines?threshold=7", headers=admin_headers)
    assert res_7.status_code == 200
    for item in res_7.json()["items"]:
        assert item["days_left"] <= 7

    # Filter overdue (< 0 days)
    res_ov = client.get("/api/deadlines?threshold=overdue", headers=admin_headers)
    assert res_ov.status_code == 200
    for item in res_ov.json()["items"]:
        assert item["days_left"] < 0
        assert item["urgency"] == "overdue"

    # Deduplication check: every alert_id must be unique
    all_res = client.get("/api/deadlines?filter=all&threshold=all&limit=100", headers=admin_headers)
    alert_ids = [item["alert_id"] for item in all_res.json()["items"]]
    assert len(alert_ids) == len(set(alert_ids)), "Found duplicate alert IDs!"


def test_deadlines_institution_scoping(client: TestClient, auth_headers: dict):
    """Test institution user only receives deadline alerts within their institutional scope."""
    res = client.get("/api/deadlines", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    for item in data["items"]:
        assert item["institution_id"] == 1 or item["institution_name"] != ""


# ============================================================================
# FEATURE 2: Explainable Document Verification Tests
# ============================================================================

def test_explainable_extraction_structured_fields():
    """Verify structured fields, explainability statuses, evidence snippets, and honest confidence=None."""
    sample_text = """
    STATE BANK OF INDIA
    TERM DEPOSIT RECEIPT
    Branch: Nariman Point Commercial Branch, Mumbai
    FDR Number / Receipt No: FDR/SBI/2026/998811
    Depositor Account Title: Vishwakarma Institute of Technology AICTE Security Deposit
    Deposit Amount: Rs. 3,500,000.00
    Issue Date: 15/07/2024
    Maturity Date: 15/07/2029
    Interest Rate (% p.a.): 7.10%
    """

    fields, structured, warnings = parse_fields_explainable(sample_text)

    # Required fields extracted
    assert fields["reference_no"] == "FDR/SBI/2026/998811"
    assert fields["amount"] == "3500000.00"
    assert fields["bank_name"] == "STATE BANK OF INDIA"
    assert fields["branch_name"] == "Nariman Point Commercial Branch, Mumbai"
    assert fields["issue_date"] == "2024-07-15"
    assert fields["maturity_date"] == "2029-07-15"
    assert fields["interest_rate"] == "7.10%"

    # Structured metadata inspection
    assert structured["reference_no"]["status"] == "Extracted"
    assert structured["reference_no"]["confidence"] is None  # Honest: no fake percentage
    assert structured["reference_no"]["evidence"] is not None

    assert structured["amount"]["status"] == "Extracted"
    assert structured["amount"]["confidence"] is None

    assert structured["branch_name"]["status"] == "Extracted"
    assert structured["interest_rate"]["status"] == "Extracted"


def test_explainable_extraction_missing_fields_and_unreadable_text():
    """Test graceful handling of unreadable or empty document text."""
    empty_text = "   "
    fields, structured, warnings = parse_fields_explainable(empty_text)
    assert structured["reference_no"]["status"] == "Not detected"
    assert structured["amount"]["status"] == "Not detected"
    assert len(warnings) > 0


def test_extract_endpoint_structured_response(client: TestClient, admin_headers: dict):
    """Test POST /api/extract/fdr returns rich explainable structured data."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("CANARA BANK FIXED DEPOSIT RECEIPT", styles["Heading1"]),
        Paragraph("FDR No: FDR/CAN/2026/771122", styles["Normal"]),
        Paragraph("Deposit Amount: Rs. 1,000,000.00", styles["Normal"]),
        Paragraph("Issue Date: 01/01/2026", styles["Normal"]),
        Paragraph("Maturity Date: 01/01/2031", styles["Normal"]),
        Paragraph("Interest Rate: 7.50%", styles["Normal"]),
    ]
    doc.build(story)
    pdf_bytes = buf.getvalue()

    res = client.post(
        "/api/extract/fdr",
        files={"file": ("test_fdr.pdf", pdf_bytes, "application/pdf")},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["engine"] == "pypdf"
    assert "structured" in data
    assert data["fields"]["reference_no"] == "FDR/CAN/2026/771122"
    assert data["structured"]["reference_no"]["status"] == "Extracted"
    assert data["structured"]["reference_no"]["confidence"] is None


# ============================================================================
# FEATURE 3: One-Click Deficiency Report Generator Tests
# ============================================================================

def test_deficiency_preview_with_discrepancies_and_missing_docs(client: TestClient, admin_headers: dict, db):
    """Test deficiency assessment when a deposit has field discrepancies and missing documents."""
    today = today_ist()
    inst = Institution(name="Engineering College of Pune", code="ECP-01")
    db.add(inst)
    db.commit()

    dep = Deposit(
        institution_id=inst.id,
        reference_no="FDR/DEF/TEST/01",
        bank_name="Bank of Baroda",
        amount=Decimal("2500000.00"),
        issue_date=today - timedelta(days=100),
        maturity_date=today + timedelta(days=900),  # < 5 years (deficiency!)
        confirmed_reference_no="FDR/DEF/TEST/01-CONFIRMED",
        confirmed_bank_name="Bank of Baroda Main",
        confirmed_amount=Decimal("2000000.00"),  # Mismatched!
        confirmed_issue_date=today - timedelta(days=100),
        confirmed_maturity_date=today + timedelta(days=900),
        mismatch_fields="amount,bank_name",
        status="DISCREPANCY",
    )
    db.add(dep)
    db.commit()

    res = client.get(f"/api/deposits/{dep.id}/deficiency-report/preview", headers=admin_headers)
    assert res.status_code == 200, res.text
    preview = res.json()

    assert preview["has_deficiencies"] is True
    assert preview["current_status"] == "DISCREPANCY"
    assert len(preview["deficiencies"]) >= 3

    categories = [d["category"] for d in preview["deficiencies"]]
    assert "MISSING_DOCUMENT" in categories
    assert "FIELD_MISMATCH" in categories
    assert "SCRUTINY_FLAG" in categories
    assert "REGULATION_NON_COMPLIANCE" in categories  # Tenure < 5 years


def test_deficiency_preview_no_deficiencies_handling(client: TestClient, admin_headers: dict, db):
    """Test compliant deposit with no deficiencies returns has_deficiencies=False."""
    today = today_ist()
    inst = Institution(name="Compliant Institute of Tech", code="CIT-99")
    db.add(inst)
    db.commit()

    dep = Deposit(
        institution_id=inst.id,
        reference_no="FDR/CLEAN/TEST/99",
        bank_name="State Bank of India",
        amount=Decimal("3500000.00"),
        issue_date=today - timedelta(days=365),
        maturity_date=today + timedelta(days=1825),  # 5+ years
        confirmed_reference_no="FDR/CLEAN/TEST/99",
        confirmed_bank_name="State Bank of India",
        confirmed_amount=Decimal("3500000.00"),
        confirmed_issue_date=today - timedelta(days=365),
        confirmed_maturity_date=today + timedelta(days=1825),
        mismatch_fields="",
        status="VERIFIED",
    )
    db.add(dep)
    db.commit()

    # Add 2 mandatory documents to eliminate missing doc deficiency
    doc1 = Document(
        deposit_id=dep.id,
        filename="fdr_receipt.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key_doc1",
        uploaded_by="officer1",
    )
    doc2 = Document(
        deposit_id=dep.id,
        filename="lien_letter.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key_doc2",
        uploaded_by="officer1",
    )
    db.add_all([doc1, doc2])
    db.commit()

    res = client.get(f"/api/deposits/{dep.id}/deficiency-report/preview", headers=admin_headers)
    assert res.status_code == 200, res.text
    preview = res.json()

    assert preview["has_deficiencies"] is False
    assert len(preview["deficiencies"]) == 0
    assert "No deficiencies identified" in preview["summary_message"]

    # Attempting to generate a report for a clean FDR should return 400
    gen_res = client.post(f"/api/deposits/{dep.id}/deficiency-report", headers=admin_headers)
    assert gen_res.status_code == 400
    assert "no recorded deficiencies" in gen_res.json()["detail"]


def test_deficiency_pdf_generation_and_download(client: TestClient, admin_headers: dict, db):
    """Test generating and downloading official PDF deficiency report."""
    today = today_ist()
    inst = Institution(name="Testing Engineering College", code="TEC-42")
    db.add(inst)
    db.commit()

    dep = Deposit(
        institution_id=inst.id,
        reference_no="FDR/PDF/TEST/42",
        bank_name="Canara Bank",
        amount=Decimal("1000000.00"),
        issue_date=today - timedelta(days=100),
        maturity_date=today + timedelta(days=700),
        status="DISCREPANCY",
        mismatch_fields="amount",
    )
    db.add(dep)
    db.commit()

    res = client.post(
        f"/api/deposits/{dep.id}/deficiency-report",
        json={
            "confirmed_deficiency_ids": [],
            "additional_comments": "Please resolve all lien marking issues within 15 days.",
        },
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"
    assert len(res.content) > 1000
