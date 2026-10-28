"""Deficiency Report Service for AICTE FDR Management Portal.

Evaluates deposits for real compliance defects:
- Missing mandatory documents (original scan, bank lien letter)
- Mismatched fields between submitted values and bank-confirmed values
- Scrutiny rejections or discrepancy flags
- Tenure inadequacy (less than 5 years)
- Open integrity findings

Generates official PDF reports via ReportLab with clear corrective actions.
"""

import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor
from ..models import AuditLog, Deposit, Document, Institution, IntegrityFinding
from ..scheduler import today_ist
from ..schemas import DeficiencyItem, DeficiencyReportGenerateIn, DeficiencyReportPreview


def assess_deposit_deficiencies(db: Session, dep: Deposit, actor: Actor) -> DeficiencyReportPreview:
    """Inspect real deposit records and compile all authentic deficiencies."""
    today = today_ist()
    inst = db.get(Institution, dep.institution_id)
    inst_name = inst.name if inst else f"Institution #{dep.institution_id}"
    inst_code = inst.code if inst else "N/A"

    deficiencies: list[DeficiencyItem] = []

    # 1. Check Missing Mandatory Documents
    docs = db.scalars(select(Document).where(Document.deposit_id == dep.id)).all()
    if not docs:
        deficiencies.append(
            DeficiencyItem(
                id="DEF-DOC-001",
                category="MISSING_DOCUMENT",
                title="Missing Original FDR / Deposit Receipt Document",
                field_name="fdr_document",
                submitted_value="None",
                verified_value="Original bank FDR scan required",
                explanation="No electronic document has been uploaded for this deposit. AICTE regulations require an authentic scan of the fixed deposit receipt.",
                required_action="Upload a clear, legible PDF scan of the original Fixed Deposit Receipt bearing the bank manager's seal.",
                severity="CRITICAL",
                is_confirmed=True,
            )
        )
    elif len(docs) == 1:
        # Check if bank lien letter exists or only 1 generic file
        deficiencies.append(
            DeficiencyItem(
                id="DEF-DOC-002",
                category="MISSING_DOCUMENT",
                title="Missing Bank Lien / Joint Operation Endorsement Letter",
                field_name="lien_letter",
                submitted_value="Single document on file",
                verified_value="Bank lien marking endorsement required",
                explanation="AICTE Approval Process Handbook (APH) mandates an explicit bank confirmation letter stating that the deposit is held in joint name with AICTE under first lien.",
                required_action="Obtain an official confirmation letter on bank letterhead confirming AICTE lien clause and upload to portal.",
                severity="HIGH",
                is_confirmed=True,
            )
        )

    # 2. Check Field Mismatches (Submitted vs Confirmed)
    if dep.mismatch_fields:
        mismatch_list = [f.strip() for f in dep.mismatch_fields.split(",") if f.strip()]
        for idx, field in enumerate(mismatch_list, start=1):
            submitted_val = getattr(dep, field, "N/A")
            confirmed_val = getattr(dep, f"confirmed_{field}", "Not verified")

            if isinstance(submitted_val, (date, datetime)):
                submitted_str = submitted_val.isoformat()
            elif isinstance(submitted_val, Decimal):
                submitted_str = f"Rs. {submitted_val:,.2f}"
            else:
                submitted_str = str(submitted_val)

            if isinstance(confirmed_val, (date, datetime)):
                confirmed_str = confirmed_val.isoformat()
            elif isinstance(confirmed_val, Decimal):
                confirmed_str = f"Rs. {confirmed_val:,.2f}"
            else:
                confirmed_str = str(confirmed_val)

            deficiencies.append(
                DeficiencyItem(
                    id=f"DEF-MISMATCH-{idx:03d}",
                    category="FIELD_MISMATCH",
                    title=f"Discrepancy in {field.replace('_', ' ').title()}",
                    field_name=field,
                    submitted_value=submitted_str,
                    verified_value=confirmed_str,
                    explanation=f"Submitted value '{submitted_str}' differs from the bank-verified value '{confirmed_str}' recorded during scrutiny.",
                    required_action=f"Reconcile {field.replace('_', ' ')} with the issuing bank branch and provide amended bank confirmation.",
                    severity="HIGH",
                    is_confirmed=True,
                )
            )

    # 3. Check Status-Based Scrutiny Issues
    if dep.status == "DISCREPANCY":
        deficiencies.append(
            DeficiencyItem(
                id="DEF-STATUS-DISCREPANCY",
                category="SCRUTINY_FLAG",
                title="Scrutiny Discrepancy Status Active",
                field_name="status",
                submitted_value=dep.status,
                verified_value="VERIFIED / COMPLIANT required",
                explanation="Scrutiny officer has marked this submission with discrepancies requiring formal institutional remediation.",
                required_action="Review officer observations and submit corrected documentation through the portal within 15 working days.",
                severity="HIGH",
                is_confirmed=True,
            )
        )
    elif dep.status == "REJECTED":
        deficiencies.append(
            DeficiencyItem(
                id="DEF-STATUS-REJECTED",
                category="SCRUTINY_FLAG",
                title="Deposit Submission Formally Rejected",
                field_name="status",
                submitted_value="REJECTED",
                verified_value="COMPLIANT required",
                explanation="This deposit has been rejected by the regulatory authority due to statutory or documentation non-compliance.",
                required_action="Submit a new valid deposit complying with all regulatory provisions.",
                severity="CRITICAL",
                is_confirmed=True,
            )
        )

    # 4. Check Tenure Adequacy (AICTE Minimum 5 Years = 1825 Days)
    tenure_days = (dep.effective_maturity - dep.issue_date).days
    if tenure_days < 1825 and dep.status not in ("RELEASED", "RENEWED"):
        deficiencies.append(
            DeficiencyItem(
                id="DEF-TENURE-SHORT",
                category="REGULATION_NON_COMPLIANCE",
                title="Inadequate Deposit Tenure (< 5 Years)",
                field_name="maturity_date",
                submitted_value=f"{tenure_days} days (~{tenure_days // 365} years)",
                verified_value="Minimum 5 years (1825 days)",
                explanation=f"Deposit tenure of {tenure_days} days is below the statutory 5-year requirement prescribed in the AICTE Approval Process Handbook.",
                required_action="Instruct issuing bank to extend or renew the FDR tenure to at least 5 years and submit updated certificate.",
                severity="CRITICAL",
                is_confirmed=True,
            )
        )

    # 5. Check Open Cross-Record Integrity Findings
    findings = db.scalars(
        select(IntegrityFinding).where(
            IntegrityFinding.primary_deposit_id == dep.id,
            IntegrityFinding.status.in_(["OPEN", "CONFIRMED_INCONSISTENCY", "UNDER_REVIEW"]),
        )
    ).all()
    for f in findings:
        deficiencies.append(
            DeficiencyItem(
                id=f"DEF-INTEGRITY-{f.id}",
                category="REGULATION_NON_COMPLIANCE",
                title=f"Cross-Record Integrity Alert: {f.category}",
                field_name="cross_record_check",
                submitted_value=dep.reference_no,
                verified_value=f.finding_code,
                explanation=f.explanation,
                required_action="Provide written clarification addressing potential duplicate reference or cross-institution lien overlap.",
                severity=f.severity,
                is_confirmed=True,
            )
        )

    # 6. Gather Reviewer Comments from Audit Trail
    audit_entries = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity == "deposit",
            AuditLog.entity_id == dep.id,
            AuditLog.action.in_(["DISCREPANCY_FLAGGED", "VERIFIED", "RENEWED", "RELEASE_DECISION"]),
        )
        .order_by(AuditLog.at.desc())
    ).all()
    reviewer_comments = [
        f"{e.actor} ({e.action} on {e.at.strftime('%d-%m-%Y')}): {e.detail}"
        for e in audit_entries
        if e.detail
    ]

    has_deficiencies = len(deficiencies) > 0
    summary_message = (
        f"Found {len(deficiencies)} actionable deficiency item(s) requiring institutional remediation."
        if has_deficiencies
        else "No deficiencies identified. This FDR record complies with current regulatory requirements and scrutiny checks."
    )

    return DeficiencyReportPreview(
        deposit_id=dep.id,
        reference_no=dep.reference_no,
        institution_name=inst_name,
        institution_code=inst_code,
        bank_name=dep.bank_name,
        amount=Decimal(dep.amount),
        issue_date=dep.issue_date,
        maturity_date=dep.effective_maturity,
        current_status=dep.status,
        has_deficiencies=has_deficiencies,
        summary_message=summary_message,
        deficiencies=deficiencies,
        reviewer_comments=reviewer_comments,
        report_date=today,
    )


def generate_deficiency_pdf(
    db: Session,
    dep: Deposit,
    actor: Actor,
    params: Optional[DeficiencyReportGenerateIn] = None,
) -> bytes:
    """Generate a clean, official government-grade PDF deficiency report."""
    preview = assess_deposit_deficiencies(db, dep, actor)
    if not preview.has_deficiencies:
        raise ValueError("Cannot generate deficiency report: this deposit has no recorded deficiencies.")

    # Filter confirmed deficiencies if specific IDs were submitted
    selected_deficiencies = preview.deficiencies
    if params and params.confirmed_deficiency_ids:
        selected_deficiencies = [
            d for d in preview.deficiencies if d.id in params.confirmed_deficiency_ids
        ]
        if not selected_deficiencies:
            selected_deficiencies = preview.deficiencies

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    header_title_style = ParagraphStyle(
        "GovHeaderTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=1,  # Center
        textColor=colors.HexColor("#0c2340"),
    )
    header_sub_style = ParagraphStyle(
        "GovHeaderSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        alignment=1,
        textColor=colors.HexColor("#475569"),
    )
    report_banner_style = ParagraphStyle(
        "ReportBanner",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=colors.HexColor("#991b1b"),
    )
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#0c2340"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1e293b"),
    )
    body_bold_style = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0c2340"),
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    story = []

    # 1. Official Header
    story.append(Paragraph("ALL INDIA COUNCIL FOR TECHNICAL EDUCATION", header_title_style))
    story.append(Paragraph("अखिल भारतीय तकनीकी शिक्षा परिषद · भारत सरकार का सांविधिक निकाय", header_sub_style))
    story.append(Paragraph("Nelson Mandela Marg, Vasant Kunj, New Delhi – 110070 | www.aicte-india.org", header_sub_style))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0c2340"), spaceAfter=8))

    # 2. Report Document Banner
    banner_data = [
        [
            Paragraph("DEFICIENCY REPORT & SCRUTINY NOTICE", report_banner_style),
        ]
    ]
    banner_table = Table(banner_data, colWidths=[520])
    banner_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
                ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#fecaca")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(banner_table)
    story.append(Spacer(1, 8))

    # 3. Section 1: Institution & Application Details
    story.append(Paragraph("1. INSTITUTION & IDENTIFICATION DETAILS", section_title_style))
    inst_data = [
        [
            Paragraph("Institution Name:", body_bold_style),
            Paragraph(preview.institution_name, body_style),
            Paragraph("Permanent Code:", body_bold_style),
            Paragraph(preview.institution_code, body_style),
        ],
        [
            Paragraph("Application / FDR ID:", body_bold_style),
            Paragraph(f"AICTE-FDR-{preview.deposit_id}", body_style),
            Paragraph("Notice Date:", body_bold_style),
            Paragraph(preview.report_date.strftime("%d-%m-%Y"), body_style),
        ],
        [
            Paragraph("Current Status:", body_bold_style),
            Paragraph(f"<b>{preview.current_status}</b>", body_style),
            Paragraph("Issuing Officer:", body_bold_style),
            Paragraph(f"{actor.name} ({actor.role})", body_style),
        ],
    ]
    inst_table = Table(inst_data, colWidths=[110, 160, 110, 140])
    inst_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(inst_table)
    story.append(Spacer(1, 8))

    # 4. Section 2: Fixed Deposit Receipt Details
    story.append(Paragraph("2. FIXED DEPOSIT RECEIPT (FDR) RECORD", section_title_style))
    fdr_data = [
        [
            Paragraph("FDR Reference No:", body_bold_style),
            Paragraph(preview.reference_no, body_style),
            Paragraph("Bank Name:", body_bold_style),
            Paragraph(preview.bank_name, body_style),
        ],
        [
            Paragraph("Deposit Amount:", body_bold_style),
            Paragraph(f"Rs. {preview.amount:,.2f}", body_style),
            Paragraph("Issue Date:", body_bold_style),
            Paragraph(preview.issue_date.strftime("%d-%m-%Y"), body_style),
        ],
        [
            Paragraph("Maturity Date:", body_bold_style),
            Paragraph(preview.maturity_date.strftime("%d-%m-%Y"), body_style),
            Paragraph("Tenure Duration:", body_bold_style),
            Paragraph(f"{(preview.maturity_date - preview.issue_date).days} days", body_style),
        ],
    ]
    fdr_table = Table(fdr_data, colWidths=[110, 160, 110, 140])
    fdr_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(fdr_table)
    story.append(Spacer(1, 8))

    # 5. Section 3: Itemized Deficiencies and Required Actions (Core Table)
    story.append(Paragraph("3. ITEMIZED DEFICIENCIES & REQUIRED CORRECTIVE ACTIONS", section_title_style))
    def_table_headers = [
        Paragraph("#", table_header_style),
        Paragraph("Category / Item", table_header_style),
        Paragraph("Observed Discrepancy", table_header_style),
        Paragraph("Severity", table_header_style),
        Paragraph("Mandatory Corrective Action", table_header_style),
    ]
    def_rows = [def_table_headers]

    for idx, d in enumerate(selected_deficiencies, start=1):
        def_rows.append(
            [
                Paragraph(str(idx), body_bold_style),
                Paragraph(f"<b>{d.title}</b><br/><font color='#64748b' size='7'>{d.category}</font>", body_style),
                Paragraph(
                    f"{d.explanation}<br/><font color='#0c2340' size='7'><b>Submitted:</b> {d.submitted_value or 'N/A'}<br/><b>Required:</b> {d.verified_value or 'N/A'}</font>",
                    body_style,
                ),
                Paragraph(
                    f"<font color='{'#991b1b' if d.severity == 'CRITICAL' else '#b45309'}'><b>{d.severity}</b></font>",
                    body_style,
                ),
                Paragraph(f"<b>{d.required_action}</b>", body_style),
            ]
        )

    def_table = Table(def_rows, colWidths=[20, 110, 175, 55, 160], repeatRows=1)
    def_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c2340")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    story.append(def_table)
    story.append(Spacer(1, 10))

    # 6. Section 4: Scrutiny Officer Remarks
    story.append(Paragraph("4. REVIEWER REMARKS & STATUTORY DIRECTIVE", section_title_style))
    custom_comments = params.additional_comments if params and params.additional_comments else ""
    directives = [
        "1. All deficiencies listed above must be rectified by the institution within 15 working days.",
        "2. Amended FDRs or bank letters must be uploaded via the AICTE FDR Management Portal.",
        "3. Failure to remediate deficiencies within the stipulated timeline may lead to regulatory withholding or hearing before the Standing Appellate Committee (SAC).",
    ]
    if custom_comments:
        directives.insert(0, f"<b>Officer Directive:</b> {custom_comments}")

    directives_data = [[Paragraph("<br/>".join(directives), body_style)]]
    directives_table = Table(directives_data, colWidths=[520])
    directives_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#fde68a")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(directives_table)
    story.append(Spacer(1, 12))

    # 7. Verification Footer & Audit
    footer_text = (
        f"Generated automatically on {datetime.now().strftime('%d-%m-%Y at %H:%M:%S IST')} by {actor.name} ({actor.role}). "
        "Computer-generated regulatory notice issued under AICTE Security Deposit Management Portal. "
        "Official endorsement valid in accordance with AICTE Approval Process Handbook."
    )
    story.append(Paragraph(footer_text, ParagraphStyle("FooterText", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))))

    doc.build(story)

    # Record Audit Event
    db.add(
        AuditLog(
            entity="deposit",
            entity_id=dep.id,
            action="DEFICIENCY_REPORT_GENERATED",
            actor=actor.name,
            detail=json.dumps(
                {
                    "deficiencies_count": len(selected_deficiencies),
                    "categories": [d.category for d in selected_deficiencies],
                    "generated_at": datetime.now().isoformat(),
                }
            ),
        )
    )
    db.commit()

    return buf.getvalue()
