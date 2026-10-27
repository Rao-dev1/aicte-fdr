"""Filtered deposit reports exported as CSV, Excel or PDF."""

import csv
import io

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Deposit

# Filter groups shown in the UI. None means no status filter.
GROUPS: dict[str, set[str] | None] = {
    "all": None,
    "active": {"ACTIVE"},
    "expiring": {"EXPIRING"},
    "matured": {"MATURED"},
    "released": {"RELEASED"},
    "pending": {"SUBMITTED", "DISCREPANCY", "RELEASE_REQUESTED"},
}

HEADERS = ["Reference", "Institution", "Bank", "Amount", "Issue date", "Maturity date", "Status", "Mismatched fields"]

MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def to_row(dep: Deposit, institution_names: dict[int, str]) -> list:
    return [
        dep.reference_no,
        institution_names.get(dep.institution_id, str(dep.institution_id)),
        dep.bank_name,
        float(dep.amount),
        dep.issue_date.isoformat(),
        dep.effective_maturity.isoformat(),
        dep.status,
        dep.mismatch_fields,
    ]


def build(fmt: str, title: str, rows: list[list]) -> bytes:
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(HEADERS)
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")

    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "FDR report"
        ws.append(HEADERS)
        for row in rows:
            ws.append(row)
        for column in ws.columns:
            width = max(len(str(cell.value or "")) for cell in column) + 2
            ws.column_dimensions[column[0].column_letter].width = min(width, 40)
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    if fmt == "pdf":
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        styles = getSampleStyleSheet()
        table = Table([HEADERS] + rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ]
            )
        )
        doc.build([Paragraph(title, styles["Title"]), Spacer(1, 12), table])
        return out.getvalue()

    raise ValueError(f"Unsupported format: {fmt}")
