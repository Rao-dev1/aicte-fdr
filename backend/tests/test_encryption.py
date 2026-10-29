from sqlalchemy import text

from app.db import SessionLocal, engine
from app.migrations import ensure_encrypted_deposit_fields
from app.models import Deposit
from tests.helpers import hdr
from tests.test_deposits import make_deposit, make_institution


def raw_row(dep_id):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT reference_no, bank_name FROM deposits WHERE id = :id"), {"id": dep_id}
        ).mappings().one()


def test_fdr_number_and_bank_are_stored_encrypted(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, ref="FDR-SECRET-1")
    row = raw_row(dep["id"])
    assert "FDR-SECRET-1" not in row["reference_no"]
    assert "State Bank" not in row["bank_name"]
    assert row["reference_no"].startswith("gAAAA")  # Fernet token


def test_the_app_still_reads_the_real_values(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, ref="FDR-READ-1")
    got = client.get(f"/api/deposits/{dep['id']}", headers=hdr("ADMIN")).json()
    assert got["reference_no"] == "FDR-READ-1"
    assert got["bank_name"] == "State Bank"


def test_duplicate_numbers_are_still_refused_ignoring_case(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-DUP")
    again = client.post(
        "/api/deposits",
        json={"institution_id": inst, "reference_no": "fdr-dup", "bank_name": "SBI", "amount": "1000",
              "issue_date": "2026-01-01", "maturity_date": "2027-01-01"},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    assert again.status_code == 409


def test_search_matches_exact_fdr_number_only(client):
    inst = make_institution(client)
    make_deposit(client, inst, ref="FDR-SEARCH-9")
    exact = client.get("/api/trace/search?q=FDR-SEARCH-9", headers=hdr("ADMIN"))
    partial = client.get("/api/trace/search?q=SEARCH", headers=hdr("ADMIN"))
    assert exact.status_code == 200, exact.text
    assert exact.json()["total"] == 1
    assert partial.json()["total"] == 0


def test_rows_saved_before_encryption_are_migrated(client):
    inst = make_institution(client)
    dep = make_deposit(client, inst, ref="FDR-OLD-PLAIN")
    # Simulate a row written before encryption existed: plain text, no lookup hash.
    with engine.begin() as conn:
        conn.execute(text("UPDATE deposits SET reference_no = 'FDR-OLD-PLAIN', bank_name = 'Old Bank', reference_hash = NULL, bank_hash = NULL WHERE id = :id"), {"id": dep["id"]})
    assert ensure_encrypted_deposit_fields() == 1
    assert raw_row(dep["id"])["reference_no"].startswith("gAAAA")
    with SessionLocal() as db:
        row = db.get(Deposit, dep["id"])
        assert row.reference_no == "FDR-OLD-PLAIN"
        assert row.bank_name == "Old Bank"
    # running again changes nothing
    assert ensure_encrypted_deposit_fields() == 0
