from tests.helpers import hdr
from tests.test_deposits import make_deposit, make_institution, verify, sweep
from datetime import date


def inbox(client, role, inst=None):
    return client.get("/api/notifications", headers=hdr(role, inst=inst)).json()


def test_new_fdr_appears_for_regulator(client):
    inst = make_institution(client)
    before = len(inbox(client, "REGULATOR_OFFICER"))
    make_deposit(client, inst, ref="FDR-NOTE-1")
    items = inbox(client, "REGULATOR_OFFICER")
    assert len(items) == before + 1
    assert "FDR-NOTE-1" in items[0]["message"]
    assert items[0]["message"].startswith("New FDR submitted")


def test_institution_sees_verification_only_for_its_own_fdr(client):
    mine = make_institution(client, "NT1")
    other = make_institution(client, "NT2")
    dep = make_deposit(client, mine, ref="FDR-NOTE-2")
    verify(client, dep["id"])
    mine_msgs = [n["message"] for n in inbox(client, "INSTITUTION_USER", inst=mine)]
    other_msgs = [n["message"] for n in inbox(client, "INSTITUTION_USER", inst=other)]
    assert any(m.startswith("Verification update") for m in mine_msgs)
    assert not any("FDR-NOTE-2" in m for m in other_msgs)


def test_renewal_request_goes_to_approver(client):
    inst = make_institution(client)
    old = make_deposit(client, inst, ref="FDR-NOTE-3", maturity="2026-11-20")
    verify(client, old["id"])
    sweep(date(2026, 11, 1))
    client.post(
        f"/api/deposits/{old['id']}/renew",
        json={"institution_id": inst, "reference_no": "FDR-NOTE-3B", "bank_name": "SBI", "amount": "1000",
              "issue_date": "2026-11-20", "maturity_date": "2027-11-20"},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    approver = inbox(client, "APPROVING_AUTHORITY")
    assert any(n["message"].startswith("Renewal awaiting approval") for n in approver)
