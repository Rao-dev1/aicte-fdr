from datetime import timedelta

import pytest

from app import sms_service
from app.db import SessionLocal
from app.models import SmsLog
from app.scheduler import today_ist
from app.sms_service import deliver_queued_sms, normalize_phone, short_var
from tests.helpers import hdr


# ---- Pure helpers ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9876543210", "919876543210"),
        ("+91 98765 43210", "919876543210"),
        ("09876543210", "919876543210"),
        ("91-9876543210", "919876543210"),
        ("5876543210", None),  # Indian mobile numbers start with 6-9
        ("98765", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_short_var_respects_dlt_limit():
    assert len(short_var("x" * 100)) <= sms_service.MAX_VAR_LEN
    assert short_var("matures in 7 days") == "matures in 7 days"


# ---- Through the API --------------------------------------------------------


def setup_institution_user_with_phone(client, phone="9876543210"):
    inst = client.post("/api/institutions", json={"name": "SMS College", "code": "SMS1"}, headers=hdr("ADMIN")).json()["id"]
    r = client.post(
        "/api/auth/users",
        json={
            "username": "smsuser",
            "full_name": "SMS User",
            "password": "Password@123",
            "role": "INSTITUTION_USER",
            "institution_id": inst,
            "phone": phone,
        },
        headers=hdr("ADMIN"),
    )
    assert r.status_code == 201, r.text
    return inst


def add_verified_deposit(client, inst, days_left):
    today = today_ist()
    dep = client.post(
        "/api/deposits",
        json={
            "institution_id": inst,
            "reference_no": "FDR-SMS-1",
            "bank_name": "State Bank",
            "amount": "5000.00",
            "issue_date": (today - timedelta(days=365)).isoformat(),
            "maturity_date": (today + timedelta(days=days_left)).isoformat(),
        },
        headers=hdr("INSTITUTION_USER", inst=inst),
    ).json()
    r = client.post(f"/api/deposits/{dep['id']}/verify", json={"observations": "ok"}, headers=hdr("REGULATOR_OFFICER"))
    assert r.status_code == 200, r.text
    return dep


def test_invalid_phone_is_rejected(client):
    inst = client.post("/api/institutions", json={"name": "Bad Phone", "code": "BP1"}, headers=hdr("ADMIN")).json()["id"]
    r = client.post(
        "/api/auth/users",
        json={"username": "badphone", "full_name": "X", "password": "Password@123", "role": "INSTITUTION_USER", "institution_id": inst, "phone": "12345"},
        headers=hdr("ADMIN"),
    )
    assert r.status_code == 422


def test_sweep_queues_sms_once_and_masks_number(client):
    inst = setup_institution_user_with_phone(client)
    add_verified_deposit(client, inst, days_left=5)

    first = client.post("/api/admin/lifecycle-sweep", headers=hdr("ADMIN")).json()
    assert first["status"] == "OK"
    assert first["sms"]["logged"] >= 1  # no MSG91 key in tests, so messages are only logged

    log = client.get("/api/admin/sms", headers=hdr("ADMIN")).json()
    mine = [row for row in log if "FDR-SMS-1" in row["message"]]
    assert mine, log
    assert all(row["status"] == "LOGGED" for row in mine)
    assert all("9876543210" not in row["to"] for row in mine)  # masked

    # Running the sweep again must not create duplicate SMS (same rule as notifications).
    client.post("/api/admin/lifecycle-sweep", headers=hdr("ADMIN"))
    again = client.get("/api/admin/sms", headers=hdr("ADMIN")).json()
    assert len([row for row in again if "FDR-SMS-1" in row["message"]]) == len(mine)


def test_sms_log_is_admin_only(client):
    assert client.get("/api/admin/sms", headers=hdr("REGULATOR_OFFICER")).status_code == 403


def test_user_without_phone_gets_no_sms(client):
    inst = client.post("/api/institutions", json={"name": "No Phone", "code": "NP1"}, headers=hdr("ADMIN")).json()["id"]
    client.post(
        "/api/auth/users",
        json={"username": "nophone", "full_name": "N", "password": "Password@123", "role": "INSTITUTION_USER", "institution_id": inst},
        headers=hdr("ADMIN"),
    )
    add_verified_deposit(client, inst, days_left=5)
    client.post("/api/admin/lifecycle-sweep", headers=hdr("ADMIN"))
    log = client.get("/api/admin/sms", headers=hdr("ADMIN")).json()
    assert not [row for row in log if "FDR-SMS-1" in row["message"]]


def test_sms_only_goes_to_the_owning_institution(client):
    inst = setup_institution_user_with_phone(client, phone="9876543210")
    other = client.post("/api/institutions", json={"name": "Other College", "code": "OTH1"}, headers=hdr("ADMIN")).json()["id"]
    client.post(
        "/api/auth/users",
        json={"username": "otheruser", "full_name": "Other", "password": "Password@123", "role": "INSTITUTION_USER", "institution_id": other, "phone": "9123456780"},
        headers=hdr("ADMIN"),
    )
    add_verified_deposit(client, inst, days_left=5)
    client.post("/api/admin/lifecycle-sweep", headers=hdr("ADMIN"))
    log = client.get("/api/admin/sms", headers=hdr("ADMIN")).json()
    recipients = {row["to"] for row in log if "FDR-SMS-1" in row["message"]}
    assert recipients == {"9198XXXXXX10"}  # only the owning institution's user, number masked


# ---- Delivery (MSG91 is faked; nothing leaves the machine) -------------------


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = b"x"

    def json(self):
        return self._body


def queue_one(db):
    row = SmsLog(to_number="919876543210", message="FDR-1|matures in 7 days", status="QUEUED")
    db.add(row)
    db.commit()
    return row.id


def test_live_delivery_sends_template_variables(client, monkeypatch):
    monkeypatch.setenv("MSG91_AUTH_KEY", "test-key")
    monkeypatch.setenv("MSG91_FLOW_ID", "flow123")
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, json=json)
        return FakeResponse(200, {"type": "success", "message": "abc"})

    monkeypatch.setattr(sms_service.httpx, "post", fake_post)
    with SessionLocal() as db:
        row_id = queue_one(db)
        counts = deliver_queued_sms(db)
        assert counts == {"sent": 1, "failed": 0, "logged": 0}
        assert db.get(SmsLog, row_id).status == "SENT"

    assert sent["headers"]["authkey"] == "test-key"
    assert sent["json"]["flow_id"] == "flow123"
    assert sent["json"]["recipients"] == [{"mobiles": "919876543210", "VAR1": "FDR-1", "VAR2": "matures in 7 days"}]


def test_provider_error_marks_failed(client, monkeypatch):
    monkeypatch.setenv("MSG91_AUTH_KEY", "test-key")
    monkeypatch.setenv("MSG91_FLOW_ID", "flow123")
    monkeypatch.setattr(sms_service.httpx, "post", lambda *a, **k: FakeResponse(400, {"type": "error", "message": "flow id missing"}))
    with SessionLocal() as db:
        row_id = queue_one(db)
        counts = deliver_queued_sms(db)
        assert counts["failed"] == 1
        row = db.get(SmsLog, row_id)
        assert row.status == "FAILED"
        assert "flow id missing" in row.error
