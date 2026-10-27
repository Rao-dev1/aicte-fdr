from datetime import date

from app.db import SessionLocal
from app.lifecycle import lifecycle_status, lifecycle_sweep


def hdr(role: str, user: str = "tester") -> dict:
    return {"X-Role": role, "X-User": user}


def sweep(on: date) -> int:
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


def verify(client, dep_id: int, confirmed: str | None = "100000.00") -> dict:
    r = client.post(
        f"/api/deposits/{dep_id}/verify",
        json={"confirmed_amount": confirmed, "observations": "checked"},
        headers=hdr("REGULATOR_OFFICER"),
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---- Scenario 1: new FDR submission --------------------------------------


def test_new_deposit_starts_as_submitted(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    assert dep["status"] == "SUBMITTED"


def test_verify_with_matching_amount_is_verified(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    assert verify(client, dep["id"])["status"] == "VERIFIED"


# ---- Scenario 2: discrepancy ---------------------------------------------


def test_verify_with_different_amount_flags_discrepancy(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    assert verify(client, dep["id"], confirmed="95000.00")["status"] == "DISCREPANCY"


# ---- Scenario 3 and 4: approaching maturity and overdue ------------------


def test_deposit_becomes_expiring_within_30_days(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, maturity="2026-11-20")
    verify(client, dep["id"])
    sweep(date(2026, 11, 1))  # 19 days before maturity
    r = client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN"))
    assert r.json()["status"] == "EXPIRING"


def test_deposit_becomes_matured_after_maturity_date(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    verify(client, dep["id"])
    sweep(date(2027, 7, 1))
    r = client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN"))
    assert r.json()["status"] == "MATURED"


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
    new = r.json()
    assert new["status"] == "SUBMITTED"
    assert new["previous_deposit_id"] == old["id"]

    old_now = client.get(f"/api/deposits/{old['id']}", headers=hdr("ADMIN")).json()
    assert old_now["status"] == "RENEWED"

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
    assert client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN")).json()["status"] == "RELEASE_REQUESTED"

    r = client.patch(
        f"/api/release-requests/{req['id']}",
        json={"approve": True, "remarks": "conditions met"},
        headers=hdr("APPROVING_AUTHORITY", "officer-2"),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"
    assert client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN")).json()["status"] == "RELEASED"


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
    assert client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN")).json()["status"] == "MATURED"


# ---- Access control and validation ---------------------------------------


def test_missing_role_header_is_unauthorized(client):
    r = client.get("/api/deposits")
    assert r.status_code == 401


def test_institution_user_cannot_verify(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst)
    r = client.post(
        f"/api/deposits/{dep['id']}/verify",
        json={"confirmed_amount": None},
        headers=hdr("INSTITUTION_USER"),
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


def test_dashboard_counts_all_statuses(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="A")
    make_deposit(client, inst, ref="B")
    body = client.get("/api/dashboard/summary", headers=hdr("ADMIN")).json()
    assert body["counts"]["SUBMITTED"] == 2
    assert body["counts"]["RELEASED"] == 0
    assert body["total"] == 2


# ---- Pure lifecycle rules ------------------------------------------------


def test_lifecycle_status_rules():
    maturity = date(2026, 12, 1)
    assert lifecycle_status("VERIFIED", maturity, date(2026, 10, 1)) == "ACTIVE"
    assert lifecycle_status("VERIFIED", maturity, date(2026, 11, 15)) == "EXPIRING"
    assert lifecycle_status("VERIFIED", maturity, date(2026, 12, 2)) == "MATURED"
    # Statuses outside the tracked set are never changed by the sweep.
    assert lifecycle_status("RENEWED", maturity, date(2026, 12, 2)) == "RENEWED"
    assert lifecycle_status("SUBMITTED", maturity, date(2026, 12, 2)) == "SUBMITTED"
