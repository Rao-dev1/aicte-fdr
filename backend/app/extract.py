"""Reads FDR documents and suggests field values. Suggestions must be checked by a person before saving.

- PDFs with a text layer are read with pypdf (no extra software needed).
- Images (PNG/JPEG) are read with Tesseract OCR, if Tesseract is installed.
- Scanned PDFs (no text layer) are not supported yet: they need a PDF-to-image step.
"""

import io
import re
from datetime import date
from typing import Optional

DATE_RE = r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{2}-\d{2})"


def _to_iso(text: str) -> Optional[str]:
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text)
    try:
        if m:
            day, month, year = (int(x) for x in m.groups())
            return date(year, month, day).isoformat()
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return date(*(int(x) for x in m.groups())).isoformat()
    except ValueError:
        return None
    return None


def _labelled_date(text: str, label: str) -> Optional[str]:
    m = re.search(label + r"[^\d\n]{0,30}" + DATE_RE, text, re.IGNORECASE)
    return _to_iso(m.group(1)) if m else None


def parse_fields(text: str) -> tuple[dict, list[str]]:
    """Pull FDR fields out of plain text. Returns (fields, warnings)."""
    warnings: list[str] = []
    fields: dict[str, Optional[str]] = {}

    m = re.search(r"(?:FDR|Receipt|Certificate)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Za-z0-9/\-]{4,})", text, re.IGNORECASE)
    fields["reference_no"] = m.group(1) if m else None

    m = re.search(r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    fields["amount"] = m.group(1).replace(",", "") if m else None

    # Matches "State Bank of India", "SAMPLE BANK LTD", "Axis Bank Limited" (the word Bank in any case).
    m = re.search(
        r"((?:[A-Z][A-Za-z&.]*[ \t]+){0,3}[A-Z][A-Za-z&.]*[ \t]+(?i:bank)(?:[ \t]+(?i:of)[ \t]+[A-Za-z]+)?(?:[ \t]+(?i:ltd|limited)\.?)?)",
        text,
    )
    fields["bank_name"] = m.group(1).strip() if m else None

    issue = _labelled_date(text, r"issue")
    maturity = _labelled_date(text, r"matur")
    if issue is None or maturity is None:
        dates = [d for d in (_to_iso(x) for x in re.findall(DATE_RE, text)) if d]
        if issue is None and dates:
            issue = dates[0]
        if maturity is None and len(dates) > 1:
            maturity = dates[1]
        warnings.append("Dates were matched by position, not by label. Check the issue and maturity dates.")
    fields["issue_date"] = issue
    fields["maturity_date"] = maturity

    if not any(fields.values()):
        warnings.append("No known fields were found in the document.")
    return fields, warnings


MAX_SCAN_PAGES = 3  # FDR details are on the first pages; this keeps OCR fast.


def _ocr_scanned_pdf(data: bytes) -> tuple[str, str, list[str]]:
    """Returns (text, engine, warnings) for a PDF with no text layer.

    Scanned PDFs hold each page as an embedded image. The images are pulled out with pypdf
    (pure Python, no extra compiled libraries) and read with Tesseract.
    """
    try:
        import pytesseract
        from PIL import Image
        from pypdf import PdfReader
    except Exception as exc:  # missing Python package
        return "", "none", [
            f"Scanned PDF reading is unavailable ({exc.__class__.__name__}). Enter the fields by hand."
        ]
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:MAX_SCAN_PAGES]:
            for image in page.images:
                pages.append(pytesseract.image_to_string(Image.open(io.BytesIO(image.data))))
        text = "\n".join(pages)
    except Exception as exc:  # Tesseract missing, or the images could not be read
        return "", "none", [
            f"Scanned PDF reading failed ({exc.__class__.__name__}). Make sure Tesseract is installed, or enter the fields by hand."
        ]
    if not text.strip():
        return "", "tesseract", ["The scanned PDF could not be read. Enter the fields by hand."]
    return text, "tesseract", []


def read_text(data: bytes, content_type: str) -> tuple[str, str, list[str]]:
    """Returns (text, engine, warnings)."""
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text, "pypdf", []
        # No text layer: the PDF is a scan. Render its pages and read them with Tesseract.
        return _ocr_scanned_pdf(data)

    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)))
        return text, "tesseract", []
    except Exception as exc:  # missing Python package, or Tesseract not installed
        return "", "none", [
            f"Image reading is unavailable ({exc.__class__.__name__}). Install Tesseract to enable it, or enter the fields by hand."
        ]


def extract_fdr(data: bytes, content_type: str) -> dict:
    text, engine, warnings = read_text(data, content_type)
    fields, field_warnings = parse_fields(text) if text.strip() else ({}, [])
    return {"engine": engine, "fields": fields, "warnings": warnings + field_warnings}
