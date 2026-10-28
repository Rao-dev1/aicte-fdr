import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.extract import parse_fields
from tests.helpers import hdr

SAMPLE_TEXT = """State Bank of India
Fixed Deposit Receipt
FDR No: FDR/2026/00123
Amount: Rs. 1,00,000.00
Issue Date: 01/06/2026
Maturity Date: 01/06/2027
"""


def make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 780
    for line in lines:
        c.drawString(60, y, line)
        y -= 22
    c.save()
    return buf.getvalue()


# ---- Login and accounts ----------------------------------------------------


def test_login_with_demo_account_returns_token_and_role(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "ADMIN"
    assert body["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"


def test_wrong_password_is_rejected(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_institution_login_carries_institution_id(client):
    r = client.post("/api/auth/login", json={"username": "institution1", "password": "Institute@12345"})
    body = r.json()
    assert body["role"] == "INSTITUTION_USER"
    assert body["institution_id"] is not None


def test_request_without_token_is_rejected_even_with_role_header(client):
    r = client.get("/api/deposits", headers={"X-Role": "ADMIN", "X-User": "hacker"})
    assert r.status_code == 401


def test_admin_can_create_user_who_can_then_log_in(client):
    r = client.post(
        "/api/auth/users",
        json={
            "username": "officer2",
            "full_name": "Second Officer",
            "email": "officer2@example.com",
            "password": "Officer2@123",
            "role": "REGULATOR_OFFICER",
        },
        headers=hdr("ADMIN"),
    )
    assert r.status_code == 201, r.text
    login = client.post("/api/auth/login", json={"username": "officer2", "password": "Officer2@123"})
    assert login.status_code == 200


def test_non_admin_cannot_create_users(client):
    r = client.post(
        "/api/auth/users",
        json={"username": "sneaky", "full_name": "X", "password": "Sneaky@123", "role": "ADMIN"},
        headers=hdr("REGULATOR_OFFICER"),
    )
    assert r.status_code == 403


# ---- Reading FDR documents -------------------------------------------------


def test_parse_fields_from_labelled_text():
    fields, warnings = parse_fields(SAMPLE_TEXT)
    assert fields["reference_no"] == "FDR/2026/00123"
    assert fields["amount"] == "100000.00"
    assert fields["bank_name"] == "State Bank of India"
    assert fields["issue_date"] == "2026-06-01"
    assert fields["maturity_date"] == "2027-06-01"
    assert warnings == []


def test_extract_endpoint_reads_text_pdf(client):
    pdf = make_pdf(SAMPLE_TEXT.splitlines())
    r = client.post(
        "/api/extract/fdr",
        files={"file": ("fdr.pdf", pdf, "application/pdf")},
        headers=hdr("INSTITUTION_USER", inst=1),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "pypdf"
    assert body["fields"]["reference_no"] == "FDR/2026/00123"
    assert body["fields"]["amount"] == "100000.00"


def test_extract_endpoint_rejects_unsupported_type(client):
    r = client.post(
        "/api/extract/fdr",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=hdr("INSTITUTION_USER", inst=1),
    )
    assert r.status_code == 415


def test_extract_endpoint_warns_on_scanned_pdf(client):
    blank = make_pdf([])  # a PDF with no text layer
    r = client.post(
        "/api/extract/fdr",
        files={"file": ("scan.pdf", blank, "application/pdf")},
        headers=hdr("INSTITUTION_USER", inst=1),
    )
    body = r.json()
    assert body["fields"] == {}
    # A blank scan has nothing for OCR to read, so the user is asked to enter the fields by hand.
    assert any("PDF" in w and "by hand" in w for w in body["warnings"])
