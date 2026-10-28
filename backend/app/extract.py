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


def _find_snippet(text: str, target: str, window: int = 50) -> Optional[str]:
    """Extract snippet of surrounding text for explainability evidence."""
    if not target or target not in text:
        return None
    idx = text.find(target)
    start = max(0, idx - window)
    end = min(len(text), idx + len(target) + window)
    raw = text[start:end].replace("\n", " ").strip()
    return f"...{raw}..." if start > 0 or end < len(text) else raw


def _labelled_date_with_evidence(text: str, label: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(label + r"[^\d\n]{0,35}" + DATE_RE, text, re.IGNORECASE)
    if m:
        iso_val = _to_iso(m.group(1))
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 20)
        snippet = text[start:end].replace("\n", " ").strip()
        return iso_val, snippet
    return None, None


def _labelled_date(text: str, label: str) -> Optional[str]:
    val, _ = _labelled_date_with_evidence(text, label)
    return val


def parse_fields_explainable(text: str) -> tuple[dict, dict, list[str]]:
    """Pull FDR fields out of plain text with explainable metadata.

    Returns:
        (fields_dict, structured_dict, warnings)
    """
    warnings: list[str] = []
    fields: dict[str, Optional[str]] = {}
    structured: dict[str, dict] = {}

    # 1. FDR Reference Number
    ref_match = re.search(
        r"(?:FDR\s*(?:Number|No\.?)|Receipt\s*(?:Number|No\.?)|Certificate\s*(?:Number|No\.?)|TDR\s*No\.?|Term\s*Deposit\s*No\.?|#)\s*[:\-]?\s*([A-Za-z0-9/\-]{4,})",
        text,
        re.IGNORECASE,
    )
    if not ref_match:
        # Fallback multi-line match
        ref_match = re.search(r"FDR\s*Number\s*[/a-zA-Z\s]*\n+([A-Za-z0-9/\-]{4,})", text, re.IGNORECASE)

    if ref_match:
        ref_val = ref_match.group(1).strip()
        fields["reference_no"] = ref_val
        structured["reference_no"] = {
            "value": ref_val,
            "status": "Extracted",
            "confidence": None,  # Honest: regex pattern, no fake percentage
            "evidence": _find_snippet(text, ref_val) or ref_match.group(0).replace("\n", " "),
        }
    else:
        fields["reference_no"] = None
        structured["reference_no"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    # 2. Deposit Amount
    amt_match = re.search(
        r"(?:Deposit\s*Amount|Principal(?:\s*Amount)?|Sum\s*of|Rs\.?|INR|₹)\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]*\d+(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if not amt_match:
        amt_match = re.search(r"(?:Rs\.?|INR|₹)\s*([\d,]*\d+(?:\.\d{1,2})?)", text, re.IGNORECASE)

    if amt_match:
        clean_amt = amt_match.group(1).replace(",", "").strip()
        fields["amount"] = clean_amt
        structured["amount"] = {
            "value": clean_amt,
            "status": "Extracted",
            "confidence": None,
            "evidence": amt_match.group(0).replace("\n", " ").strip(),
        }
    else:
        fields["amount"] = None
        structured["amount"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    # 3. Bank Name
    bank_match = re.search(
        r"((?:STATE\s*BANK\s*OF\s*INDIA|PUNJAB\s*NATIONAL\s*BANK|BANK\s*OF\s*BARODA|CANARA\s*BANK|HDFC\s*BANK|ICICI\s*BANK|AXIS\s*BANK|UNION\s*BANK\s*OF\s*INDIA|CENTRAL\s*BANK\s*OF\s*INDIA|INDIAN\s*BANK|(?:[A-Z][A-Za-z&.]*[ \t]+){0,3}(?i:bank)(?:[ \t]+(?i:of)[ \t]+[A-Za-z]+)?(?:[ \t]+(?i:ltd|limited)\.?)?))",
        text,
    )
    if bank_match:
        bank_val = bank_match.group(1).strip()
        fields["bank_name"] = bank_val
        structured["bank_name"] = {
            "value": bank_val,
            "status": "Extracted",
            "confidence": None,
            "evidence": _find_snippet(text, bank_val),
        }
    else:
        fields["bank_name"] = None
        structured["bank_name"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    # 4. Branch Name
    branch_match = re.search(r"(?:Branch|Br\.)\s*[:\-]?\s*([A-Za-z0-9\s,\.\-]{3,50}?)(?:\s*\||\n|$)", text, re.IGNORECASE)
    if branch_match:
        br_val = branch_match.group(1).strip()
        fields["branch_name"] = br_val
        structured["branch_name"] = {
            "value": br_val,
            "status": "Extracted",
            "confidence": None,
            "evidence": branch_match.group(0).strip(),
        }
    else:
        fields["branch_name"] = None
        structured["branch_name"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    # 5. Institution Name / Depositor Title
    inst_match = re.search(
        r"(?:Depositor\s*Account\s*Title|Favoring|In\s*the\s*name\s*of|Account\s*Title|Name\s*of\s*Depositor|Institution)\s*[:\-]?\s*\n*([A-Za-z0-9\s,\.\-&()]{5,90}?)(?:\n|Deposit\s*Amount|$)",
        text,
        re.IGNORECASE,
    )
    if inst_match:
        inst_val = inst_match.group(1).strip()
        fields["institution_name"] = inst_val
        structured["institution_name"] = {
            "value": inst_val,
            "status": "Extracted",
            "confidence": None,
            "evidence": inst_match.group(0).replace("\n", " ").strip(),
        }
    else:
        fields["institution_name"] = None
        structured["institution_name"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    # 6. Issue & Maturity Dates
    issue, issue_evidence = _labelled_date_with_evidence(text, r"issue")
    maturity, maturity_evidence = _labelled_date_with_evidence(text, r"matur")

    issue_status = "Extracted" if issue else "Not detected"
    mat_status = "Extracted" if maturity else "Not detected"

    if issue is None or maturity is None:
        dates = [d for d in (_to_iso(x) for x in re.findall(DATE_RE, text)) if d]
        if issue is None and dates:
            issue = dates[0]
            issue_evidence = f"Positional date match from document: {dates[0]}"
            issue_status = "Needs review"
        if maturity is None and len(dates) > 1:
            maturity = dates[1]
            maturity_evidence = f"Positional date match from document: {dates[1]}"
            mat_status = "Needs review"
        warnings.append("Dates were matched by position, not by explicit label. Verify the issue and maturity dates.")

    fields["issue_date"] = issue
    fields["maturity_date"] = maturity

    structured["issue_date"] = {
        "value": issue,
        "status": issue_status,
        "confidence": None,
        "evidence": issue_evidence,
    }
    structured["maturity_date"] = {
        "value": maturity,
        "status": mat_status,
        "confidence": None,
        "evidence": maturity_evidence,
    }

    # 7. Interest Rate
    roi_match = re.search(r"(?:Interest\s*Rate|ROI|Rate\s*of\s*Interest|Int\.\s*Rate)\s*[:\-\(%\sa-zA-Z\.\)]*[:\-]?\s*(\d+(?:\.\d{1,2})?)\s*%", text, re.IGNORECASE)
    if roi_match:
        roi_val = f"{roi_match.group(1)}%"
        fields["interest_rate"] = roi_val
        structured["interest_rate"] = {
            "value": roi_val,
            "status": "Extracted",
            "confidence": None,
            "evidence": roi_match.group(0).strip(),
        }
    else:
        fields["interest_rate"] = None
        structured["interest_rate"] = {
            "value": None,
            "status": "Not detected",
            "confidence": None,
            "evidence": None,
        }

    if not any(fields.values()):
        warnings.append("No known FDR fields could be detected in the document text.")

    return fields, structured, warnings


def parse_fields(text: str) -> tuple[dict, list[str]]:
    """Legacy compatibility helper returning (fields, warnings)."""
    fields, _, warnings = parse_fields_explainable(text)
    return fields, warnings


MAX_SCAN_PAGES = 3  # FDR details are on the first pages; this keeps OCR fast.


def _ocr_scanned_pdf(data: bytes) -> tuple[str, str, list[str]]:
    """Returns (text, engine, warnings) for a PDF with no text layer."""
    try:
        import pytesseract
        from PIL import Image
        from pypdf import PdfReader
    except Exception as exc:
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
    except Exception as exc:
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
        # No text layer: scanned PDF
        return _ocr_scanned_pdf(data)

    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)))
        return text, "tesseract", []
    except Exception as exc:
        return "", "none", [
            f"Image reading is unavailable ({exc.__class__.__name__}). Install Tesseract to enable it, or enter the fields by hand."
        ]


def extract_fdr(data: bytes, content_type: str) -> dict:
    text, engine, warnings = read_text(data, content_type)
    fields, structured, field_warnings = parse_fields_explainable(text) if text.strip() else ({}, {}, [])
    return {
        "engine": engine,
        "fields": fields,
        "structured": structured,
        "warnings": warnings + field_warnings,
        "text_preview": text[:500] if text else "",
    }
