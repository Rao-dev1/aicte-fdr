from datetime import date

from app.db import SessionLocal
from app.lifecycle import lifecycle_status, lifecycle_sweep
from tests.helpers import hdr


def sweep(on: date) -> dict:
    with SessionLocal() as db:
        return lifecycle_sweep(db, on)


def make_institution(client, code: str = "TC01") -> int:
    r = client.post("/api/institutions", json={"name": f"College {code}", "code": code}, headers=hdr("ADMIN"))
    assert r.status_code == 201, r.text
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
        headers=hdr("INSTITUTION_USER", inst=inst_id),
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


# ---- New FDR and verification ---------------------------------------------


def test_new_deposit_starts_as_submitted(client):
    inst = make_institution(client)
    assert make_deposit(client, inst)["status"] == "SUBMITTED"


def test_verify_with_all_matching_is_verified(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    body = verify(
        client,
        dep["id"],
        confirmed_reference_no="FDR-1",
        confirmed_bank_name="State Bank",
        confirmed_amount="100000.00",
    )
    assert body["status"] == "VERIFIED"
    assert body["mismatch_fields"] == []


def test_amount_mismatch_flags_discrepancy(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    body = verify(client, dep["id"], confirmed_amount="95000.00")
    assert body["status"] == "DISCREPANCY"
    assert body["mismatch_fields"] == ["amount"]
    assert body["amount"] == "100000.00"
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


# ---- Maturity, reminders, overdue -----------------------------------------


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

    notes = client.get("/api/notifications", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    kinds = sorted(n["kind"] for n in notes if n["deposit_id"] == dep["id"])
    assert kinds == ["REMINDER_30", "REMINDER_60", "REMINDER_7"]


def test_overdue_escalates_to_approving_authority_only(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    authority = client.get("/api/notifications", headers=hdr("APPROVING_AUTHORITY")).json()
    assert any(n["kind"] == "OVERDUE" and n["deposit_id"] == dep["id"] for n in authority)

    institution = client.get("/api/notifications", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert not any(n["kind"] == "OVERDUE" for n in institution)


def test_notification_can_be_marked_read(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])
    sweep(date(2026, 10, 25))
    note = client.get("/api/notifications", headers=hdr("INSTITUTION_USER", inst=inst)).json()[0]
    r = client.patch(f"/api/notifications/{note['id']}/read", headers=hdr("INSTITUTION_USER", inst=inst))
    assert r.status_code == 200
    assert r.json()["is_read"] is True


def test_reminder_emails_are_logged_for_the_owning_institution_only(client):
    inst = make_institution(client)
    owner = client.post(
        "/api/auth/users",
        json={
            "username": "owner1",
            "full_name": "Owner",
            "email": "owner1@example.com",
            "password": "Password@123",
            "role": "INSTITUTION_USER",
            "institution_id": inst,
        },
        headers=hdr("ADMIN"),
    )
    assert owner.status_code == 201, owner.text
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])
    result = sweep(date(2026, 9, 25))
    assert result["emails"]["logged"] >= 1

    emails = client.get("/api/admin/emails", headers=hdr("ADMIN")).json()
    assert any(e["to"] == "owner1@example.com" and e["status"] == "LOGGED" for e in emails)
    # The seeded demo user belongs to a different institution and must not be emailed about this FDR.
    assert not any(e["to"] == "institution1@example.com" for e in emails)


# ---- Renewal and release --------------------------------------------------


def propose_renewal(client, inst, old_id, ref="FDR-NEW"):
    return client.post(
        f"/api/deposits/{old_id}/renew",
        json={
            "institution_id": inst,
            "reference_no": ref,
            "bank_name": "State Bank",
            "amount": "100000.00",
            "issue_date": "2026-11-20",
            "maturity_date": "2027-11-20",
        },
        headers=hdr("INSTITUTION_USER", inst=inst),
    )


def test_renewal_waits_for_approval_then_marks_old_renewed(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-OLD", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))

    r = propose_renewal(client, inst, old["id"])
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "PENDING"
    assert get_status(client, old["id"]) != "RENEWED"

    rid = r.json()["id"]
    approved = client.patch(
        f"/api/renewal-requests/{rid}",
        json={"approve": True, "remarks": "ok"},
        headers=hdr("APPROVING_AUTHORITY"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert get_status(client, old["id"]) == "RENEWED"

    created = approved.json()["created_deposit_id"]
    new = client.get(f"/api/deposits/{created}", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert new["previous_deposit_id"] == old["id"]
    assert new["reference_no"] == "FDR-NEW"

    history = client.get(f"/api/deposits/{old['id']}/history", headers=hdr("ADMIN")).json()
    assert any(entry["action"] == "RENEWED" for entry in history)


def test_rejected_renewal_leaves_the_fdr_unchanged(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-KEEP", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))
    before = get_status(client, old["id"])

    rid = propose_renewal(client, inst, old["id"], ref="FDR-NOPE").json()["id"]
    r = client.patch(f"/api/renewal-requests/{rid}", json={"approve": False, "remarks": "wrong amount"}, headers=hdr("APPROVING_AUTHORITY"))
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert get_status(client, old["id"]) == before
    # the number is still free, so a corrected request can be made
    assert propose_renewal(client, inst, old["id"], ref="FDR-NOPE").status_code == 201


def test_only_one_renewal_can_wait_at_a_time(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-ONE", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))
    assert propose_renewal(client, inst, old["id"], ref="FDR-A").status_code == 201
    assert propose_renewal(client, inst, old["id"], ref="FDR-B").status_code == 409


def test_institution_cannot_approve_its_own_renewal(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-SELF", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))
    rid = propose_renewal(client, inst, old["id"], ref="FDR-X").json()["id"]
    r = client.patch(f"/api/renewal-requests/{rid}", json={"approve": True}, headers=hdr("INSTITUTION_USER", inst=inst))
    assert r.status_code == 403
def test_release_request_approved_sets_released(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    r = client.post(f"/api/deposits/{dep['id']}/release", headers=hdr("INSTITUTION_USER", inst=inst))
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "PENDING"
    assert get_status(client, dep["id"]) == "RELEASE_REQUESTED"

    pending = client.get("/api/release-requests", headers=hdr("APPROVING_AUTHORITY")).json()
    assert any(p["id"] == req["id"] for p in pending)

    r = client.patch(
        f"/api/release-requests/{req['id']}",
        json={"approve": True, "remarks": "conditions met"},
        headers=hdr("APPROVING_AUTHORITY", "approver1"),
    )
    assert r.json()["status"] == "APPROVED"
    assert get_status(client, dep["id"]) == "RELEASED"


def test_release_rejected_restores_previous_status(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))

    req = client.post(f"/api/deposits/{dep['id']}/release", headers=hdr("INSTITUTION_USER", inst=inst)).json()
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
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "fdr.pdf"
    assert doc["size_bytes"] == len(content)

    got = client.get(f"/api/documents/{doc['id']}/download", headers=hdr("ADMIN"))
    assert got.status_code == 200
    assert got.content == content


def test_unsupported_file_type_is_rejected(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    r = client.post(
        f"/api/deposits/{dep['id']}/documents",
        files={"file": ("notes.exe", b"MZ", "application/octet-stream")},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    assert r.status_code == 415


# ---- Reports, calendar, dashboard -----------------------------------------


def test_pending_report_exports_csv_xlsx_and_pdf(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-REPORT")

    csv_r = client.get("/api/reports/deposits?group=pending&format=csv", headers=hdr("REGULATOR_OFFICER"))
    assert csv_r.status_code == 200
    assert "FDR-REPORT" in csv_r.text

    xlsx_r = client.get("/api/reports/deposits?group=pending&format=xlsx", headers=hdr("REGULATOR_OFFICER"))
    assert xlsx_r.content[:2] == b"PK"

    pdf_r = client.get("/api/reports/deposits?group=pending&format=pdf", headers=hdr("APPROVING_AUTHORITY"))
    assert pdf_r.content[:4] == b"%PDF"


def test_report_is_forbidden_for_institution_users(client):
    r = client.get("/api/reports/deposits?group=all&format=csv", headers=hdr("INSTITUTION_USER", inst=1))
    assert r.status_code == 403


def test_calendar_lists_maturities_in_range(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-CAL", maturity="2026-11-20")
    r = client.get("/api/calendar?start=2026-11-01&end=2026-11-30", headers=hdr("INSTITUTION_USER", inst=inst))
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


def test_missing_token_is_unauthorized(client):
    assert client.get("/api/deposits").status_code == 401


def test_institution_user_cannot_verify(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    r = client.post(f"/api/deposits/{dep['id']}/verify", json={}, headers=hdr("INSTITUTION_USER", inst=inst))
    assert r.status_code == 403


def test_institution_user_cannot_see_another_institutions_deposit(client):
    inst_a = make_institution(client, "AAA1")
    inst_b = make_institution(client, "BBB1")
    dep = make_deposit(client, inst_a, ref="FDR-A")

    assert client.get(f"/api/deposits/{dep['id']}", headers=hdr("INSTITUTION_USER", inst=inst_b)).status_code == 404
    listed = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=inst_b)).json()
    assert listed["total"] == 0
    assert client.get(f"/api/deposits/{dep['id']}", headers=hdr("INSTITUTION_USER", inst=inst_a)).status_code == 200


def test_institution_user_cannot_create_for_another_institution(client):
    inst_a = make_institution(client, "AAA1")
    inst_b = make_institution(client, "BBB1")
    r = client.post(
        "/api/deposits",
        json={
            "institution_id": inst_a,
            "reference_no": "FDR-X",
            "bank_name": "X",
            "amount": "1.00",
            "issue_date": "2026-06-01",
            "maturity_date": "2027-06-01",
        },
        headers=hdr("INSTITUTION_USER", inst=inst_b),
    )
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
        headers=hdr("INSTITUTION_USER", inst=inst),
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
        headers=hdr("INSTITUTION_USER", inst=inst),
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


def test_amount_with_commas_and_symbols_is_accepted(client):
    inst = make_institution(client, code="TC-AMT")
    for amt_input, expected in [
        ("10,000.00", "10000.00"),
        ("10,000,00", "10000.00"),
        ("1,00,000", "100000.00"),
        ("Rs. 35,00,000.00", "3500000.00"),
    ]:
        ref = f"FDR-AMT-{abs(hash(amt_input)) % 100000}"
        r = client.post(
            "/api/deposits",
            json={
                "institution_id": inst,
                "reference_no": ref,
                "bank_name": "State Bank of India",
                "amount": amt_input,
                "issue_date": "2024-01-01",
                "maturity_date": "2029-01-01",
            },
            headers=hdr("INSTITUTION_USER", inst=inst),
        )
        assert r.status_code == 201, f"Failed for {amt_input}: {r.text}"
        body = r.json()
        assert float(body["amount"]) == float(expected)


def test_zero_and_negative_amounts_rejected(client):
    inst = make_institution(client, code="TC-BAD")
    for bad in ["0", "0.00", "-500", "-10,000"]:
        r = client.post(
            "/api/deposits",
            json={
                "institution_id": inst,
                "reference_no": "FDR-FAIL",
                "bank_name": "State Bank of India",
                "amount": bad,
                "issue_date": "2024-01-01",
                "maturity_date": "2029-01-01",
            },
            headers=hdr("INSTITUTION_USER", inst=inst),
        )
        assert r.status_code == 422, f"Expected 422 for amount {bad}, got {r.status_code}"

