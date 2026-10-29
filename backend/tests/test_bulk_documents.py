import io
import json

from app import extract
from tests.helpers import hdr
from tests.test_bulk_import import make_institution


def fake_extract(monkeypatch):
    monkeypatch.setattr(
        extract,
        "extract_fdr",
        lambda data, content_type: {"engine": "test", "fields": json.loads(data), "warnings": []},
    )


def make_deposit(client, inst, ref):
    r = client.post(
        "/api/deposits",
        json={"institution_id": inst, "reference_no": ref, "bank_name": "SBI", "amount": "1000",
              "issue_date": "2026-01-01", "maturity_date": "2027-01-01"},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def bulk(client, files, inst, deposit_id=None):
    payload = [("files", (name, data, ctype)) for name, data, ctype in files]
    form = {"deposit_id": str(deposit_id)} if deposit_id else {}
    return client.post("/api/documents/bulk", files=payload, data=form, headers=hdr("INSTITUTION_USER", inst=inst))


def test_files_are_attached_by_fdr_number(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "BD1")
    dep = make_deposit(client, inst, "FDR-777")
    r = bulk(client, [("fdr-777.png", b'{"amount": "1000"}', "image/png")], inst)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attached"] == 1
    assert body["results"][0]["deposit_id"] == dep
    docs = client.get(f"/api/deposits/{dep}/documents", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert len(docs) == 1 and docs[0]["version"] == 1


def test_unknown_numbers_are_reported_not_saved(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "BD2")
    make_deposit(client, inst, "FDR-1")
    r = bulk(client, [("FDR-1.png", b"{}", "image/png"), ("FDR-99.png", b"{}", "image/png")], inst)
    body = r.json()
    assert (body["attached"], body["unmatched"]) == (1, 1)
    assert [x["status"] for x in body["results"]] == ["attached", "unmatched"]


def test_bad_file_type_is_rejected_per_file(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "BD3")
    make_deposit(client, inst, "FDR-5")
    r = bulk(client, [("FDR-5.txt", b"hello", "text/plain"), ("FDR-5.png", b"{}", "image/png")], inst)
    body = r.json()
    assert body["rejected"] == 1
    assert body["attached"] == 1


def test_other_institutions_fdrs_are_not_matched(client, monkeypatch):
    fake_extract(monkeypatch)
    owner = make_institution(client, "BD4")
    other = make_institution(client, "BD5")
    make_deposit(client, owner, "FDR-42")
    r = bulk(client, [("FDR-42.png", b"{}", "image/png")], other)
    assert r.json()["unmatched"] == 1


def test_one_fdr_can_be_chosen_for_all_files(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "BD6")
    dep = make_deposit(client, inst, "FDR-8")
    r = bulk(client, [("scan1.png", b"{}", "image/png"), ("scan2.png", b"{}", "image/png")], inst, deposit_id=dep)
    assert r.json()["attached"] == 2
