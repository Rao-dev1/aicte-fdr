import io

from openpyxl import Workbook

from app.bulk_import import check_rows, parse_date, read_table
from tests.helpers import hdr

HEADER = "reference_no,bank_name,amount,issue_date,maturity_date"


def csv_file(*lines):
    return "\n".join([HEADER, *lines]).encode()


def upload(client, path, data, name="fdrs.csv", inst=None, role="INSTITUTION_USER", **extra):
    return client.post(
        path,
        files={"file": (name, data, "text/csv")},
        data={k: str(v) for k, v in extra.items()},
        headers=hdr(role, inst=inst),
    )


def make_institution(client, code):
    r = client.post("/api/institutions", json={"name": f"College {code}", "code": code}, headers=hdr("ADMIN"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_csv_rows_are_read_with_header_aliases():
    rows = read_table(b"FDR No,Bank,Amount,Issue Date,Maturity\nF1,SBI,\"1,00,000\",2026-01-01,2027-01-01\n", "x.csv")
    assert rows == [{"reference_no": "F1", "bank_name": "SBI", "amount": "1,00,000", "issue_date": "2026-01-01", "maturity_date": "2027-01-01"}]


def test_missing_column_is_reported():
    try:
        read_table(b"reference_no,bank_name\nF1,SBI\n", "x.csv")
        assert False, "should have raised"
    except ValueError as exc:
        assert "amount" in str(exc)


def test_wrong_file_type_is_refused():
    try:
        read_table(b"whatever", "x.txt")
        assert False
    except ValueError as exc:
        assert ".csv or .xlsx" in str(exc)


def test_xlsx_is_read():
    wb = Workbook()
    ws = wb.active
    ws.append(["reference_no", "bank_name", "amount", "issue_date", "maturity_date"])
    from datetime import date

    ws.append(["X1", "Canara Bank", 250000, date(2026, 5, 1), date(2027, 5, 1)])
    buf = io.BytesIO()
    wb.save(buf)
    rows = read_table(buf.getvalue(), "fdrs.xlsx")
    assert rows[0]["issue_date"] == "2026-05-01"
    assert check_rows(rows, set())[0]["errors"] == []


def test_row_checks_report_each_problem():
    rows = [
        {"reference_no": "", "bank_name": "SBI", "amount": "abc", "issue_date": "nope", "maturity_date": "2026-01-01"},
        {"reference_no": "EXISTS", "bank_name": "SBI", "amount": "10", "issue_date": "2026-02-01", "maturity_date": "2026-01-01"},
        {"reference_no": "DUP", "bank_name": "SBI", "amount": "10", "issue_date": "2026-01-01", "maturity_date": "2027-01-01"},
        {"reference_no": "DUP", "bank_name": "SBI", "amount": "10", "issue_date": "2026-01-01", "maturity_date": "2027-01-01"},
    ]
    results = check_rows(rows, {"exists"})
    assert "FDR number is missing" in results[0]["errors"]
    assert "Amount is not a valid number" in results[0]["errors"]
    assert any("not recognised" in e for e in results[0]["errors"])
    assert "Maturity date must be after the issue date" in results[1]["errors"]
    assert "This FDR number is already in the portal" in results[1]["errors"]
    assert results[2]["errors"] == []
    assert results[3]["errors"] == ["This FDR number also appears on line 4 of the file"]


def test_dates_in_indian_format_are_accepted():
    assert parse_date("15/05/2026").isoformat() == "2026-05-15"
    assert parse_date("31-02-2026") is None


def test_preview_saves_nothing_and_flags_bad_rows(client):
    inst = make_institution(client, "BI1")
    data = csv_file("F-100,SBI,500000,2026-04-01,2027-04-01", "F-101,SBI,0,2026-04-01,2027-04-01")
    r = upload(client, "/api/deposits/import/preview", data, inst=inst, institution_id=inst)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["total"], body["valid"], body["invalid"]) == (2, 1, 1)
    listed = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert listed["total"] == 0


def test_confirm_creates_all_rows_when_valid(client):
    inst = make_institution(client, "BI2")
    data = csv_file("B-1,SBI,500000,2026-04-01,2027-04-01", "B-2,Canara Bank,\"2,50,000.50\",15/05/2026,15/05/2027")
    r = upload(client, "/api/deposits/import/confirm", data, inst=inst, institution_id=inst)
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 2
    listed = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert listed["total"] == 2


def test_confirm_saves_nothing_if_any_row_is_bad(client):
    inst = make_institution(client, "BI3")
    data = csv_file("C-1,SBI,500000,2026-04-01,2027-04-01", "C-2,,500,2026-04-01,2027-04-01")
    r = upload(client, "/api/deposits/import/confirm", data, inst=inst, institution_id=inst)
    assert r.status_code == 422
    listed = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=inst)).json()
    assert listed["total"] == 0


def test_institution_user_cannot_import_for_another_institution(client):
    mine = make_institution(client, "BI4")
    other = make_institution(client, "BI5")
    data = csv_file("D-1,SBI,500000,2026-04-01,2027-04-01")
    r = upload(client, "/api/deposits/import/confirm", data, inst=mine, institution_id=other)
    assert r.status_code == 201
    other_list = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=other)).json()
    assert other_list["total"] == 0
    mine_list = client.get("/api/deposits", headers=hdr("INSTITUTION_USER", inst=mine)).json()
    assert mine_list["total"] == 1


def test_template_download(client):
    r = client.get("/api/deposits/import/template", headers=hdr("INSTITUTION_USER", inst=make_institution(client, "BI6")))
    assert r.status_code == 200
    assert r.text.startswith("reference_no,bank_name,amount,issue_date,maturity_date")
