#!/usr/bin/env python3
"""Generates realistic sample FDR documents in PDF format for the AICTE FDR Portal.
All documents contain valid text layers compatible with pypdf and the FDR field extraction engine.
"""

import os
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

SAMPLE_DIR = Path("/Users/manasvilomate/Desktop/aicte-fdr/sample_documents")
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def draw_fdr_certificate(
    filename: str,
    bank_name: str,
    branch_name: str,
    fdr_no: str,
    cust_id: str,
    joint_names: str,
    amount_num: str,
    amount_words: str,
    interest_rate: str,
    issue_date: str,
    maturity_date: str,
    tenure: str,
    special_clause: str,
    header_color=colors.HexColor("#0f2d52"),
    secondary_color=colors.HexColor("#123a6b"),
):
    pdf_path = SAMPLE_DIR / filename
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    # Outer decorative border
    c.setStrokeColor(header_color)
    c.setLineWidth(2)
    c.rect(30, 30, width - 60, height - 60)
    c.setLineWidth(0.8)
    c.rect(34, 34, width - 68, height - 68)

    # Header Banner
    c.setFillColor(header_color)
    c.rect(35, height - 110, width - 70, 75, fill=True, stroke=False)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 65, bank_name.upper())

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, height - 85, "TERM DEPOSIT ADVICE / FIXED DEPOSIT RECEIPT")

    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, height - 100, f"Branch: {branch_name} | IFSC: {bank_name[:4].upper()}0001234")

    # Lien Marking Badge
    c.setFillColor(colors.HexColor("#fff2f0"))
    c.setStrokeColor(colors.HexColor("#d9363e"))
    c.setLineWidth(1)
    c.roundRect(45, height - 150, width - 90, 26, 4, fill=True, stroke=True)

    c.setFillColor(colors.HexColor("#a8071a"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, height - 142, "*** SECURITY DEPOSIT IN JOINT NAME OF AICTE & INSTITUTION - UNDER LIEN ***")

    # Key Metadata Table Grid
    start_y = height - 175
    row_height = 24
    table_x = 45
    table_w = width - 90

    rows = [
        ("FDR Number / Receipt No:", fdr_no, "Customer ID (CIF):", cust_id),
        ("Depositor Account Title:", joint_names, None, None),
        ("Deposit Amount:", f"Rs. {amount_num}", "Amount in Words:", amount_words),
        ("Issue Date:", issue_date, "Maturity Date:", maturity_date),
        ("Tenure / Term:", tenure, "Interest Rate (% p.a.):", interest_rate),
        ("Operating Instructions:", "Jointly operated with AICTE authorization", "Auto-Renewal Status:", "Under AICTE Lien Clause"),
    ]

    curr_y = start_y
    c.setFont("Helvetica", 9.5)

    for row in rows:
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.setLineWidth(0.6)

        if row[2] is None:
            # Full width row
            c.rect(table_x, curr_y - row_height, table_w, row_height, fill=True, stroke=True)
            c.setFillColor(colors.HexColor("#334155"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(table_x + 8, curr_y - 16, row[0])
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica", 8.5)
            c.drawString(table_x + 160, curr_y - 16, str(row[1]))
        else:
            half_w = table_w / 2
            # Left Cell
            c.rect(table_x, curr_y - row_height, half_w, row_height, fill=True, stroke=True)
            c.setFillColor(colors.HexColor("#334155"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(table_x + 8, curr_y - 16, row[0])
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica", 9)
            c.drawString(table_x + 140, curr_y - 16, str(row[1]))

            # Right Cell
            c.setFillColor(colors.HexColor("#f8fafc"))
            c.rect(table_x + half_w, curr_y - row_height, half_w, row_height, fill=True, stroke=True)
            c.setFillColor(colors.HexColor("#334155"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(table_x + half_w + 8, curr_y - 16, row[2])
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont("Helvetica", 8.5)
            c.drawString(table_x + half_w + 130, curr_y - 16, str(row[3]))

        curr_y -= row_height

    # Endorsement and Special Clause Section
    curr_y -= 15
    c.setFillColor(colors.HexColor("#f1f5f9"))
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.rect(table_x, curr_y - 90, table_w, 90, fill=True, stroke=True)

    c.setFillColor(secondary_color)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(table_x + 10, curr_y - 20, "LIEN CLAUSE & CONDITIONS GOVERNING AICTE SECURITY DEPOSIT:")

    c.setFillColor(colors.HexColor("#1e293b"))
    c.setFont("Helvetica", 8.5)
    clause_lines = [
        "1. This Fixed Deposit Receipt is earmarked as Security Deposit for All India Council for Technical Education (AICTE).",
        "2. The Bank undertakes not to encash, disburse, advance loan or create third-party encumbrance without prior",
        "   written clearance/discharge order from the authorized officer of AICTE.",
        f"3. {special_clause}",
        "4. This deposit shall be subject to rules and regulations as notified under the AICTE Approval Process Handbook (APH).",
    ]
    sub_y = curr_y - 35
    for line in clause_lines:
        c.drawString(table_x + 10, sub_y, line)
        sub_y -= 12

    # Verification / Extraction Helper Text (formatted so pypdf extracts labels cleanly)
    curr_y -= 115
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.rect(table_x, curr_y - 50, table_w, 50, fill=True, stroke=True)
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(table_x + 8, curr_y - 14, "SYSTEM MACHINE READABLE SUMMARY (AICTE PORTAL OCR COMPATIBLE):")
    c.setFont("Helvetica", 8)
    c.drawString(
        table_x + 8,
        curr_y - 28,
        f"FDR No: {fdr_no} | Bank: {bank_name} | Amount: Rs. {amount_num}",
    )
    c.drawString(
        table_x + 8,
        curr_y - 42,
        f"Issue Date: {issue_date} | Maturity Date: {maturity_date} | Status: VERIFIABLE",
    )

    # Signatures and Bank Seal
    curr_y -= 85
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.line(table_x + 30, curr_y, table_x + 180, curr_y)
    c.line(table_w - 180 + table_x, curr_y, table_w - 30 + table_x, curr_y)

    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(table_x + 105, curr_y - 12, "Authorized Signatory (Bank Officer)")
    c.drawCentredString(table_x + 105, curr_y - 24, f"For {bank_name}")

    c.drawCentredString(table_w - 105 + table_x, curr_y - 12, "Branch Manager / Chief Manager")
    c.drawCentredString(table_w - 105 + table_x, curr_y - 24, "Official Bank Stamp & Seal")

    # Seal Simulation
    c.setStrokeColor(colors.HexColor("#1e3a8a"))
    c.setLineWidth(1.5)
    c.circle(width / 2, curr_y - 15, 26)
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawCentredString(width / 2, curr_y - 6, f"{bank_name.upper()[:16]}")
    c.drawCentredString(width / 2, curr_y - 16, "VERIFIED LIEN")
    c.drawCentredString(width / 2, curr_y - 26, "BRANCH OFFICE")

    # Footer note
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(width / 2, 45, "Computer generated Term Deposit Receipt. Certified copy under Bankers' Books Evidence Act, 1891.")

    c.save()
    print(f"Generated: {pdf_path}")


def draw_lien_confirmation_letter(filename: str):
    pdf_path = SAMPLE_DIR / filename
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    # Header
    c.setFillColor(colors.HexColor("#0f2d52"))
    c.rect(0, height - 90, width, 90, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 45, "STATE BANK OF INDIA")
    c.setFont("Helvetica", 9)
    c.drawString(50, height - 65, "Nariman Point Commercial Branch, Mumbai - 400021 | Email: sbi.00123@sbi.co.in")

    # Letter Details
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 120, "Ref No: SBI/NP/AICTE/LIEN/2026/044")
    c.setFont("Helvetica", 10)
    c.drawString(width - 160, height - 120, "Date: 15/07/2024")

    # Recipient
    to_lines = [
        "To,",
        "The Regional Officer,",
        "Western Regional Office (WRO),",
        "All India Council for Technical Education (AICTE),",
        "Industrial Assurance Building, Churchgate, Mumbai - 400 020.",
    ]
    y = height - 150
    for line in to_lines:
        c.drawString(50, y, line)
        y -= 14

    # Subject
    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Subject: Confirmation of FDR Creation and Lien Marking in favour of AICTE")
    c.line(50, y - 2, 450, y - 2)

    # Body
    y -= 25
    c.setFont("Helvetica", 9.5)
    body_paragraphs = [
        "Dear Sir/Madam,",
        "",
        "This is to certify that at the request of Vishwakarma Institute of Technology, Pune (VIT Pune),",
        "we have opened the following Fixed Deposit with our branch under joint lien in favour of AICTE:",
        "",
        "  1. FDR No: FDR/SBI/2026/884920",
        "  2. Bank Name: State Bank of India",
        "  3. Principal Amount: Rs. 35,00,000.00 (Rupees Thirty Five Lakhs Only)",
        "  4. Issue Date: 15/07/2024",
        "  5. Maturity Date: 15/07/2029",
        "  6. Period: 5 Years (60 Months)",
        "  7. Joint Depositor: The Regional Officer AICTE WRO & The Principal, VIT Pune",
        "",
        "We hereby confirm that the Bank has recorded the exclusive lien and charge in favor of AICTE in",
        "our Core Banking System (CBS). We undertake not to allow any prepayment, loan against FDR, premature",
        "encashment, or transfer without prior written sanction and release order from your office.",
        "",
        "This confirmation letter is issued on official request for submission to AICTE FDR Management Portal.",
        "",
        "Yours faithfully,",
        "For State Bank of India,",
    ]
    for line in body_paragraphs:
        c.drawString(50, y, line)
        y -= 14

    # Signatures
    y -= 40
    c.drawString(50, y, "Authorized Branch Manager")
    c.drawString(50, y - 12, "State Bank of India, Nariman Point Branch")

    c.save()
    print(f"Generated: {pdf_path}")


def main():
    # 1. Fresh Valid 5-Year FDR (State Bank of India, Rs. 35 Lakhs)
    draw_fdr_certificate(
        filename="1_SBI_FDR_35Lakhs_Fresh_Valid.pdf",
        bank_name="State Bank of India",
        branch_name="Nariman Point Commercial Branch, Mumbai",
        fdr_no="FDR/SBI/2026/884920",
        cust_id="CIF908821948",
        joint_names="Regional Officer AICTE WRO & Principal, Vishwakarma Institute of Technology",
        amount_num="3,500,000.00",
        amount_words="Rupees Thirty Five Lakhs Only",
        interest_rate="7.10%",
        issue_date="15/07/2024",
        maturity_date="15/07/2029",
        tenure="5 Years (60 Months)",
        special_clause="Auto-renewal for consecutive 5-year periods until formal release order from AICTE.",
    )

    # 2. Renewal FDR (Punjab National Bank, Rs. 15 Lakhs)
    draw_fdr_certificate(
        filename="2_PNB_FDR_15Lakhs_Renewal.pdf",
        bank_name="Punjab National Bank",
        branch_name="Deccan Gymkhana Branch, Pune",
        fdr_no="FDR/PNB/2026/301984",
        cust_id="CIF441920831",
        joint_names="Regional Officer AICTE & VIT Pune Accounts (Renewal of FDR/PNB/2021/110294)",
        amount_num="1,500,000.00",
        amount_words="Rupees Fifteen Lakhs Only",
        interest_rate="7.25%",
        issue_date="10/01/2026",
        maturity_date="10/01/2031",
        tenure="5 Years (60 Months)",
        special_clause="Renewal FDR issued in continuation of prior deposit FDR/PNB/2021/110294 under AICTE lien.",
        header_color=colors.HexColor("#7c1a22"),
        secondary_color=colors.HexColor("#991b1b"),
    )

    # 3. Discrepancy FDR (Bank of Baroda, Short Tenure - 3 Years instead of 5)
    draw_fdr_certificate(
        filename="3_BOB_FDR_25Lakhs_Discrepancy_ShortTenure.pdf",
        bank_name="Bank of Baroda",
        branch_name="Shivaji Nagar Branch, Pune",
        fdr_no="FDR/BOB/2025/551203",
        cust_id="CIF773291044",
        joint_names="Vishwakarma Institute of Technology (Solo account - Missing AICTE Joint Mandate)",
        amount_num="2,500,000.00",
        amount_words="Rupees Twenty Five Lakhs Only",
        interest_rate="6.85%",
        issue_date="01/03/2025",
        maturity_date="01/03/2028",
        tenure="3 Years (36 Months - Non-compliant with 5-year APH mandate)",
        special_clause="WARNING: Solo title holder without explicit AICTE Joint Lien registration.",
        header_color=colors.HexColor("#c2410c"),
        secondary_color=colors.HexColor("#ea580c"),
    )

    # 4. Replacement / PG Program 8-Year FDR (HDFC Bank Ltd, Rs. 50 Lakhs)
    draw_fdr_certificate(
        filename="4_HDFC_FDR_50Lakhs_PG_Program_8Years.pdf",
        bank_name="HDFC Bank Ltd",
        branch_name="Kothrud Branch, Pune",
        fdr_no="FDR/HDFC/2026/772109",
        cust_id="CIF109923841",
        joint_names="Regional Officer AICTE WRO & Secretary, B.R. Educational Trust",
        amount_num="5,000,000.00",
        amount_words="Rupees Fifty Lakhs Only",
        interest_rate="7.40%",
        issue_date="20/05/2025",
        maturity_date="20/05/2033",
        tenure="8 Years (96 Months)",
        special_clause="Long-term security deposit for approval of Postgraduate and Integrated Technical Programs.",
        header_color=colors.HexColor("#004c8f"),
        secondary_color=colors.HexColor("#0284c7"),
    )

    # 5. Expiring Soon FDR (Canara Bank, Rs. 10 Lakhs - Due within 30 days)
    draw_fdr_certificate(
        filename="5_CANARA_FDR_10Lakhs_Expiring_Soon.pdf",
        bank_name="Canara Bank",
        branch_name="Camp Branch, Pune",
        fdr_no="FDR/CAN/2021/660421",
        cust_id="CIF556102934",
        joint_names="Regional Officer AICTE & Principal, VIT Pune",
        amount_num="1,000,000.00",
        amount_words="Rupees Ten Lakhs Only",
        interest_rate="6.90%",
        issue_date="01/11/2021",
        maturity_date="15/11/2026",
        tenure="5 Years (Maturity approaching within 30 days)",
        special_clause="Maturity check trigger: Institution must submit Renewal FDR or apply for formal release.",
        header_color=colors.HexColor("#0369a1"),
        secondary_color=colors.HexColor("#0284c7"),
    )

    # 6. Official Bank Lien Confirmation Letter
    draw_lien_confirmation_letter("6_Bank_Lien_Confirmation_Letter.pdf")


if __name__ == "__main__":
    main()
