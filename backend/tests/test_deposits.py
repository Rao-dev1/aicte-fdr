from datetime import date

from app.db import SessionLocal
from app.lifecycle import lifecycle_status, lifecycle_sweep


def hdr(role: str, user: str = "tester") -> dict:
    return {"X-Role": role, "X-User": user}


def sweep(on: date) -> dict:
    with SessionLocal() as db:
        return lifecycle_sweep(db, on)


def make_institution(client) -> int:
    r = client.post("/api/institutions", json={"name": "Test College", "code": "TC01"}, headers=hdr("ADMIN"))
    assert r.status_code == 201
    return r.json()["id"]


def make_deposit(client, inst_id: int, ref: str = "FDR-1", maturity: str = "2027-06-01") -> dict:
    r = client.post(
        "/api/deposits",
        json={
            "institution_id": inst_id,
            "reference_no": ref,
            "bank_name": "State Bank",
            "amount": "100000.00",
            "issue_date": "2026-06-01",
            "maturity_date": maturity,
        },
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 201, r.text
    return r.json()


def verify(client, dep_id: int, **confirmed) -> dict:
    payload = {"confirmed_amount": "100000.00", "observations": "checked"} if not confirmed else confirmed
    r = client.post(f"/api/deposits/{dep_id}/verify", json=payload, headers=hdr("REGULATOR_OFFICER"))
    assert r.status_code == 200, r.text
    return r.json()


def get_status(client, dep_id: int) -> str:
    return client.get(f"/api/deposits/{dep_id}", headers=hdr("ADMIN")).json()["status"]


# ---- Scenario 1: new FDR submission --------------------------------------


def test_new_deposit_starts_as_submitted(client):
    inst = make_institution(client)
    assert make_deposit(client, inst)["status"] == "SUBMITTED"


def test_verify_with_all_matching_is_verified(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    body = verify(client, dep["id"], confirmed_reference_no="FDR-1", confirmed_bank_name="State Bank", confirmed_amount="100000.00")
    assert body["status"] == "VERIFIED"
    assert body["mismatch_fields"] == []


# ---- Scenario 2: discrepancy, field by field ------------------------------


def test_amount_mismatch_flags_discrepancy(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    body = verify(client, dep["id"], confirmed_amount="95000.00")
    assert body["status"] == "DISCREPANCY"
    assert body["mismatch_fields"] == ["amount"]
    assert body["amount"] == "100000.00"  # submitted value is kept
    assert body["confirmed_amount"] == "95000.00"


def test_each_mismatching_field_is_listed(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    body = verify(
        client,
        dep["id"],
        confirmed_reference_no="FDR-X",
        confirmed_bank_name="Canara Bank",
        confirmed_maturity_date="2027-06-05",
    )
    assert body["status"] == "DISCREPANCY"
    assert body["mismatch_fields"] == ["reference_no", "bank_name", "maturity_date"]
    assert body["reference_no"] == "FDR-1"
    assert body["bank_name"] == "State Bank"


def test_reverify_after_fix_clears_discrepancy(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"], confirmed_amount="95000.00")
    body = verify(client, dep["id"], confirmed_amount="100000.00")
    assert body["status"] == "VERIFIED"
    assert body["mismatch_fields"] == []


# ---- Scenario 3 and 4: maturity, expiry and overdue ----------------------


def test_deposit_becomes_expiring_within_30_days(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])
    sweep(date(2026, 11, 1))
    assert get_status(client, dep["id"]) == "EXPIRING"


def test_deposit_becomes_matured_after_maturity_date(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))
    assert get_status(client, dep["id"]) == "MATURED"


def test_reminders_fire_once_at_60_30_and_7_days(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])

    sweep(date(2026, 9, 25))  # 56 days left
    assert sweep(date(2026, 9, 25))["notifications_created"] == 0  # no duplicate on a re-run

    sweep(date(2026, 10, 25))  # 26 days left
    sweep(date(2026, 11, 15))  # 5 days left

    notes = client.get("/api/notifications", headers=hdr("INSTITUTION_USER")).json()
    kinds = sorted(n["kind"] for n in notes if n["deposit_id"] == dep["id"])
    assert kinds == ["REMINDER_30", "REMINDER_60", "REMINDER_7"]


def test_overdue_escalates_to_approving_authority_only(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    authority = client.get("/api/notifications", headers=hdr("APPROVING_AUTHORITY")).json()
    assert any(n["kind"] == "OVERDUE" and n["deposit_id"] == dep["id"] for n in authority)

    institution = client.get("/api/notifications", headers=hdr("INSTITUTION_USER")).json()
    assert not any(n["kind"] == "OVERDUE" for n in institution)


def test_notification_can_be_marked_read(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])
    sweep(date(2026, 10, 25))
    note = client.get("/api/notifications", headers=hdr("INSTITUTION_USER")).json()[0]
    r = client.patch(f"/api/notifications/{note['id']}/read", headers=hdr("INSTITUTION_USER"))
    assert r.status_code == 200
    assert r.json()["is_read"] is True


# ---- Scenario 5: renewal -------------------------------------------------


def test_renewal_marks_old_renewed_and_links_new(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-OLD", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))

    r = client.post(
        f"/api/deposits/{old['id']}/renew",
        json={
            "institution_id": inst,
            "reference_no": "FDR-NEW",
            "bank_name": "State Bank",
            "amount": "100000.00",
            "issue_date": "2026-11-20",
            "maturity_date": "2027-11-20",
        },
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["previous_deposit_id"] == old["id"]
    assert get_status(client, old["id"]) == "RENEWED"

    history = client.get(f"/api/deposits/{old['id']}/history", headers=hdr("ADMIN")).json()
    assert any(entry["action"] == "RENEWED" for entry in history)


# ---- Scenario 6: release workflow ----------------------------------------


def test_release_request_approved_sets_released(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    r = client.post(f"/api/deposits/{dep['id']}/release", headers=hdr("INSTITUTION_USER"))
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "PENDING"
    assert get_status(client, dep["id"]) == "RELEASE_REQUESTED"

    pending = client.get("/api/release-requests", headers=hdr("APPROVING_AUTHORITY")).json()
    assert any(p["id"] == req["id"] for p in pending)

    r = client.patch(
        f"/api/release-requests/{req['id']}",
        json={"approve": True, "remarks": "conditions met"},
        headers=hdr("APPROVING_AUTHORITY", "officer-2"),
    )
    assert r.json()["status"] == "APPROVED"
    assert get_status(client, dep["id"]) == "RELEASED"


def test_release_rejected_restores_previous_status(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    req = client.post(f"/api/deposits/{dep['id']}/release", headers=hdr("INSTITUTION_USER")).json()
    client.patch(
        f"/api/release-requests/{req['id']}",
        json={"approve": False, "remarks": "documents missing"},
        headers=hdr("APPROVING_AUTHORITY"),
    )
    assert get_status(client, dep["id"]) == "MATURED"


# ---- Documents -----------------------------------------------------------


def test_pdf_upload_and_download_round_trip(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    content = b"%PDF-1.4 sample fdr"
    r = client.post(
        f"/api/deposits/{dep['id']}/documents",
        files={"file": ("fdr.pdf", content, "application/pdf")},
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "fdr.pdf"
    assert doc["size_bytes"] == len(content)

    listed = client.get(f"/api/deposits/{dep['id']}/documents", headers=hdr("ADMIN")).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    got = client.get(f"/api/documents/{doc['id']}/download", headers=hdr("ADMIN"))
    assert got.status_code == 200
    assert got.content == content


def test_unsupported_file_type_is_rejected(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    r = client.post(
        f"/api/deposits/{dep['id']}/documents",
        files={"file": ("notes.exe", b"MZ", "application/octet-stream")},
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 415


# ---- Reports, calendar, dashboard ----------------------------------------


def test_pending_report_exports_csv_xlsx_and_pdf(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-REPORT")

    csv_r = client.get("/api/reports/deposits?group=pending&format=csv", headers=hdr("REGULATOR_OFFICER"))
    assert csv_r.status_code == 200
    assert "FDR-REPORT" in csv_r.text

    xlsx_r = client.get("/api/reports/deposits?group=pending&format=xlsx", headers=hdr("REGULATOR_OFFICER"))
    assert xlsx_r.status_code == 200
    assert xlsx_r.content[:2] == b"PK"  # xlsx is a zip container

    pdf_r = client.get("/api/reports/deposits?group=pending&format=pdf", headers=hdr("APPROVING_AUTHORITY"))
    assert pdf_r.status_code == 200
    assert pdf_r.content[:4] == b"%PDF"


def test_report_is_forbidden_for_institution_users(client):
    r = client.get("/api/reports/deposits?group=all&format=csv", headers=hdr("INSTITUTION_USER"))
    assert r.status_code == 403


def test_calendar_lists_maturities_in_range(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-CAL", maturity="2026-11-20")
    r = client.get("/api/calendar?start=2026-11-01&end=2026-11-30", headers=hdr("INSTITUTION_USER"))
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["on_date"] == "2026-11-20"
    assert events[0]["reference_no"] == "FDR-CAL"


def test_dashboard_counts_and_pending_approvals(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="A")
    make_deposit(client, inst, ref="B")
    body = client.get("/api/dashboard/summary", headers=hdr("ADMIN")).json()
    assert body["counts"]["SUBMITTED"] == 2
    assert body["total"] == 2
    assert body["pending_approvals"] == 0


# ---- Access control and validation ---------------------------------------


def test_missing_role_header_is_unauthorized(client):
    assert client.get("/api/deposits").status_code == 401


def test_institution_user_cannot_verify(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    r = client.post(f"/api/deposits/{dep['id']}/verify", json={}, headers=hdr("INSTITUTION_USER"))
    assert r.status_code == 403


def test_duplicate_reference_is_rejected(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-DUP")
    r = client.post(
        "/api/deposits",
        json={
            "institution_id": inst,
            "reference_no": "FDR-DUP",
            "bank_name": "X",
            "amount": "1.00",
            "issue_date": "2026-06-01",
            "maturity_date": "2027-06-01",
        },
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 409


def test_maturity_before_issue_is_rejected(client):
    inst = make_institution(client)
    r = client.post(
        "/api/deposits",
        json={
            "institution_id": inst,
            "reference_no": "FDR-BAD",
            "bank_name": "X",
            "amount": "1.00",
            "issue_date": "2027-06-01",
            "maturity_date": "2026-06-01",
        },
        headers=hdr("INSTITUTION_USER"),
    )
    assert r.status_code == 422


# ---- Pure lifecycle rules ------------------------------------------------


def test_lifecycle_status_rules():
    maturity = date(2026, 12, 1)
    assert lifecycle_status("VERIFIED", maturity, date(2026, 10, 1)) == "ACTIVE"
    assert lifecycle_status("VERIFIED", maturity, date(2026, 11, 15)) == "EXPIRING"
    assert lifecycle_status("VERIFIED", maturity, date(2026, 12, 2)) == "MATURED"
    assert lifecycle_status("RENEWED", maturity, date(2026, 12, 2)) == "RENEWED"
    assert lifecycle_status("SUBMITTED", maturity, date(2026, 12, 2)) == "SUBMITTED"
