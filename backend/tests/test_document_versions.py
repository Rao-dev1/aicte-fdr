import json

from app import extract
from tests.helpers import hdr


def fake_extract(monkeypatch):
    """The file contents are JSON with the values to 'read'. OCR is not needed for these tests."""
    monkeypatch.setattr(
        extract,
        "extract_fdr",
        lambda data, content_type: {"engine": "test", "fields": json.loads(data), "warnings": []},
    )


def make_institution(client, code):
    r = client.post("/api/institutions", json={"name": f"College {code}", "code": code}, headers=hdr("ADMIN"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_deposit(client, inst, ref="FDR-V1"):
    r = client.post(
        "/api/deposits",
        json={
            "institution_id": inst,
            "reference_no": ref,
            "bank_name": "State Bank",
            "amount": "100000.00",
            "issue_date": "2026-06-01",
            "maturity_date": "2027-06-01",
        },
        headers=hdr("INSTITUTION_USER", inst=inst),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(client, dep, fields, inst):
    return client.post(
        f"/api/deposits/{dep}/documents",
        files={"file": ("scan.png", json.dumps(fields).encode(), "image/png")},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )


def new_version(client, dep, doc_id, fields, inst):
    return client.post(
        f"/api/deposits/{dep}/documents/{doc_id}/versions",
        files={"file": ("scan-v2.png", json.dumps(fields).encode(), "image/png")},
        headers=hdr("INSTITUTION_USER", inst=inst),
    )


def test_new_version_keeps_every_earlier_version(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "VER1")
    dep = make_deposit(client, inst)
    v1 = upload(client, dep, {"amount": "100000.00", "issue_date": "2026-06-01"}, inst).json()

    r = new_version(client, dep, v1["id"], {"amount": "150000.00", "issue_date": "2026-06-01"}, inst)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2
    assert r.json()["series_id"] == v1["series_id"]

    versions = client.get(f"/api/documents/{v1['id']}/versions", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert [v["version"] for v in versions] == [1, 2]


def test_compare_lists_only_the_values_that_changed(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "VER2")
    dep = make_deposit(client, inst)
    v1 = upload(client, dep, {"amount": "100000.00", "issue_date": "2026-06-01"}, inst).json()
    v2 = new_version(client, dep, v1["id"], {"amount": "150000.00", "issue_date": "2026-06-01"}, inst).json()

    r = client.get(f"/api/documents/compare?a={v1['id']}&b={v2['id']}", headers=hdr("REGULATOR_OFFICER"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changes"] == [{"field": "amount", "old": "100000.00", "new": "150000.00"}]
    assert body["identical_values"] is False


def test_earlier_version_file_can_still_be_downloaded(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "VER3")
    dep = make_deposit(client, inst)
    v1 = upload(client, dep, {"amount": "100000.00"}, inst).json()
    new_version(client, dep, v1["id"], {"amount": "150000.00"}, inst)

    r = client.get(f"/api/documents/{v1['id']}/download", headers=hdr("INSTITUTION_USER", inst=inst))
    assert r.status_code == 200
    assert json.loads(r.content) == {"amount": "100000.00"}


def test_other_institution_cannot_see_versions_or_compare(client, monkeypatch):
    fake_extract(monkeypatch)
    owner = make_institution(client, "VER4")
    other = make_institution(client, "VER5")
    dep = make_deposit(client, owner)
    v1 = upload(client, dep, {"amount": "100000.00"}, owner).json()
    v2 = new_version(client, dep, v1["id"], {"amount": "150000.00"}, owner).json()

    outsider = hdr("INSTITUTION_USER", inst=other)
    assert client.get(f"/api/documents/{v1['id']}/versions", headers=outsider).status_code == 404
    assert client.get(f"/api/documents/compare?a={v1['id']}&b={v2['id']}", headers=outsider).status_code == 404
    assert new_version(client, dep, v1["id"], {"amount": "1"}, other).status_code == 404


def test_compare_refuses_documents_from_different_fdrs(client, monkeypatch):
    fake_extract(monkeypatch)
    inst = make_institution(client, "VER6")
    dep1 = make_deposit(client, inst, ref="FDR-A")
    dep2 = make_deposit(client, inst, ref="FDR-B")
    doc1 = upload(client, dep1, {"amount": "100000.00"}, inst).json()
    doc2 = upload(client, dep2, {"amount": "100000.00"}, inst).json()

    r = client.get(f"/api/documents/compare?a={doc1['id']}&b={doc2['id']}", headers=hdr("REGULATOR_OFFICER"))
    assert r.status_code == 404
