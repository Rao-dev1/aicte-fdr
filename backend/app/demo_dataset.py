"""Demonstration Dataset for AICTE Security Deposit / FDR Management Portal.

Populates a comprehensive, interconnected dataset across all four core features:
1. FDR TRACE (Lineage chains, multi-generation renewals, replacements, hash-chained journals)
2. Release Readiness Graph (Fully satisfied, missing docs, premature term, active integrity anomaly, discrepancy)
3. Regulation Replay (Versioned rules, immutable historical snapshots, flipping compliance outcomes)
4. Cross-Record Integrity Network (Cross-institution duplicate numbers, date conflicts, bank mismatches, invalid predecessor links)

All records tagged with:
"DEMO DATA — NOT VERIFIED BANK OR INSTITUTION RECORDS"
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import os
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .crypto import fdr_number_hash
from .models import (
    AssessmentSnapshot,
    Deposit,
    Document,
    FDRLifecycleEvent,
    FDRLineageRelation,
    Institution,
    IntegrityFinding,
    IntegrityFindingAction,
    RegulationRule,
    ReleaseReadinessEvaluation,
    ReleaseRequest,
    User,
    utcnow,
)
from .services import (
    integrity_service,
    readiness_service,
    regulation_service,
    trace_service,
)
from .storage import save as storage_save

log = logging.getLogger("fdr.demo_dataset")

DEMO_TAG = "DEMO DATA — NOT VERIFIED BANK OR INSTITUTION RECORDS"

# 10 Fictional Institutions
INSTITUTIONS_DATA = [
    {"code": "DIT-PUNE", "name": "Vishwakarma Institute of Technology, Pune"},
    {"code": "WVCE-NASHIK", "name": "Western Valley College of Engineering, Nashik"},
    {"code": "SIAS-KOLHAPUR", "name": "Sahyadri Institute of Applied Sciences, Kolhapur"},
    {"code": "CTU-GOA", "name": "Coastal Technical University, Goa"},
    {"code": "CICT-NAGPUR", "name": "Central India College of Technology, Nagpur"},
    {"code": "RIE-INDORE", "name": "Riverbend Institute of Engineering, Indore"},
    {"code": "HPI-AURANGABAD", "name": "Horizon Polytechnic Institute, Aurangabad"},
    {"code": "MCT-BENGALURU", "name": "Meridian College of Technology, Bengaluru"},
    {"code": "NIE-HYDERABAD", "name": "Northstar Institute of Engineering, Hyderabad"},
    {"code": "GTC-BHOPAL", "name": "Greenfield Technical College, Bhopal"},
]

# 6 Fictional Banks
BANKS = [
    "Western Deccan Cooperative Bank",
    "Meridian Commercial Bank",
    "National Valley Bank",
    "Horizon Urban Bank",
    "Pioneer Financial Bank",
    "Central Crest Bank",
]

# Sample minimal PDF binary content for demo documents
SAMPLE_PDF_HEADER = b"%PDF-1.4\n1 0 obj\n<< /Title (AICTE FDR Document - DEMO) /Creator (AICTE Portal) >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def _ts(d: date, hour: int = 10, minute: int = 0) -> datetime:
    """Helper to convert date to UTC datetime with specific hour."""
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc)


def seed_institutions(db: Session) -> dict[str, Institution]:
    """Ensures the 10 institutions exist. Updates Institution #1 if present."""
    inst_map: dict[str, Institution] = {}

    # Check institution 1
    inst1 = db.get(Institution, 1)
    if inst1:
        inst1.code = "DIT-PUNE"
        inst1.name = "Vishwakarma Institute of Technology, Pune"
        db.flush()
        inst_map["DIT-PUNE"] = inst1

    for item in INSTITUTIONS_DATA:
        code = item["code"]
        if code in inst_map:
            continue
        existing = db.scalar(select(Institution).where(Institution.code == code))
        if not existing:
            inst = Institution(code=code, name=item["name"])
            db.add(inst)
            db.flush()
            inst_map[code] = inst
        else:
            existing.name = item["name"]
            inst_map[code] = existing

    db.commit()
    return inst_map


def seed_users(db: Session, inst_map: dict[str, Institution]) -> None:
    """Seeds standard demo users and institution-specific accounts."""
    users_to_ensure = [
        ("admin", "Portal Admin", "ADMIN", None, "Admin@12345"),
        ("officer1", "AICTE Regulation Officer", "REGULATOR_OFFICER", None, "Officer@12345"),
        ("approver1", "Approving Authority", "APPROVING_AUTHORITY", None, "Approver@12345"),
        ("institution1", "Vishwakarma Institute Accounts", "INSTITUTION_USER", "DIT-PUNE", "Institute@12345"),
        ("institution2", "Western Valley Accounts", "INSTITUTION_USER", "WVCE-NASHIK", "Institute@12345"),
        ("institution3", "Sahyadri Institute Accounts", "INSTITUTION_USER", "SIAS-KOLHAPUR", "Institute@12345"),
        ("institution4", "Coastal Technical Accounts", "INSTITUTION_USER", "CTU-GOA", "Institute@12345"),
    ]

    for uname, full_name, role, code, pwd in users_to_ensure:
        u = db.scalar(select(User).where(User.username == uname))
        inst_id = inst_map[code].id if code and code in inst_map else None
        if not u:
            db.add(
                User(
                    username=uname,
                    full_name=full_name,
                    email=f"{uname}@example.com",
                    role=role,
                    institution_id=inst_id,
                    password_hash=hash_password(pwd),
                    is_active=True,
                )
            )
        else:
            if inst_id is not None:
                u.institution_id = inst_id
            u.full_name = full_name
    db.commit()


def seed_regulations(db: Session) -> dict[str, RegulationRule]:
    """Ensures all standard versioned rules exist."""
    regulation_service.ensure_default_regulations_seeded(db)
    rules = db.scalars(select(RegulationRule)).all()
    rule_map = {f"{r.rule_code}:{r.version}": r for r in rules}
    return rule_map


def seed_demonstration_dataset(db: Session) -> dict[str, Any]:
    """Main orchestrator seeding 38 interconnected FDR records across all 4 features."""
    inst_map = seed_institutions(db)
    seed_users(db, inst_map)
    rule_map = seed_regulations(db)

    # Reference today as 2026-10-29
    today = date(2026, 10, 29)

    # Dictionary of created deposits by reference_no for lineage/predecessor resolution
    created_deposits: dict[str, Deposit] = {}
    existing_all = db.scalars(select(Deposit)).all()
    for d in existing_all:
        created_deposits[d.reference_no] = d

    # Deposit Specifications (~38 Records)
    # Fields:
    # ref, inst_code, bank, amount, issue_date, maturity_date, status,
    # confirmed_bank, confirmed_amount, confirmed_issue, confirmed_mat, mismatch_fields,
    # pred_ref, lineage_rel, docs, rel_req, snapshots
    DEPOSITS_SPEC = [
        # ======================================================================
        # 1. DECCAN INSTITUTE OF TECHNOLOGY, PUNE (DIT-PUNE) - 7 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-DIT-101",
            "inst_code": "DIT-PUNE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1500000.00"),
            "issue_date": date(2023, 5, 10),
            "maturity_date": date(2028, 5, 10),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1500000.00"),
            "confirmed_issue": date(2023, 5, 10),
            "confirmed_mat": date(2028, 5, 10),
            "mismatch_fields": "",
            "docs": [
                ("FDR_Receipt_DIT_101.pdf", "application/pdf"),
                ("Bank_Lien_Confirmation_DIT_101.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2023:2.0.0:COMPLIANT"],
            "summary": "Baseline verified active deposit under Western Deccan Cooperative Bank.",
        },
        {
            "ref": "DEMO-FDR-DIT-102",
            "inst_code": "DIT-PUNE",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2021, 11, 2),
            "maturity_date": date(2026, 11, 2),  # 4 days to maturity!
            "status": "ACTIVE",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("2500000.00"),
            "confirmed_issue": date(2021, 11, 2),
            "confirmed_mat": date(2026, 11, 2),
            "mismatch_fields": "",
            "docs": [
                ("FDR_Receipt_DIT_102.pdf", "application/pdf"),
                ("Bank_Lien_Notice_DIT_102.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": [],
            "summary": "Urgent maturity alert: Matures in 4 days. Scheduled for renewal processing.",
        },
        {
            "ref": "DEMO-FDR-DIT-103",
            "inst_code": "DIT-PUNE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1000000.00"),
            "issue_date": date(2016, 4, 15),
            "maturity_date": date(2021, 4, 15),
            "status": "RENEWED",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1000000.00"),
            "confirmed_issue": date(2016, 4, 15),
            "confirmed_mat": date(2021, 4, 15),
            "mismatch_fields": "",
            "docs": [("Historical_FDR_DIT_103.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Generation 1 (Root): Original 5-year security deposit created in 2016.",
        },
        {
            "ref": "DEMO-FDR-DIT-104",
            "inst_code": "DIT-PUNE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1200000.00"),
            "issue_date": date(2021, 4, 15),
            "maturity_date": date(2026, 4, 15),
            "status": "RENEWED",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1200000.00"),
            "confirmed_issue": date(2021, 4, 15),
            "confirmed_mat": date(2026, 4, 15),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-DIT-103",
            "lineage_rel": "RENEWAL",
            "docs": [("Renewal_Certificate_DIT_104.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Generation 2: First 5-year renewal with accrued augmentation to ₹12 Lakhs.",
        },
        {
            "ref": "DEMO-FDR-DIT-105",
            "inst_code": "DIT-PUNE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1500000.00"),
            "issue_date": date(2026, 4, 15),
            "maturity_date": date(2031, 4, 15),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1500000.00"),
            "confirmed_issue": date(2026, 4, 15),
            "confirmed_mat": date(2031, 4, 15),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-DIT-104",
            "lineage_rel": "RENEWAL",
            "docs": [
                ("Renewal_Certificate_DIT_105.pdf", "application/pdf"),
                ("Lien_Endorsement_DIT_105.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Generation 3 (Current Active Leaf): Second 5-year renewal maturing in 2031.",
        },
        {
            "ref": "DEMO-FDR-DIT-106",
            "inst_code": "DIT-PUNE",
            "bank": "Central Crest Bank",
            "amount": Decimal("800000.00"),
            "issue_date": date(2024, 3, 1),
            "maturity_date": date(2029, 3, 1),
            "status": "DISCREPANCY",
            "confirmed_bank": "Central Crest Bank",
            "confirmed_amount": Decimal("750000.00"),  # Mismatch: ₹8L vs ₹7.5L
            "confirmed_issue": date(2024, 3, 1),
            "confirmed_mat": date(2029, 3, 1),
            "mismatch_fields": "amount",
            "docs": [("FDR_Submitted_DIT_106.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2023:2.0.0:NON_COMPLIANT"],
            "summary": "Discrepancy flag: Submitted ₹8,00,000 but bank confirmed ₹7,50,000. Scrutiny blocker.",
        },
        {
            "ref": "DEMO-FDR-WDC-884920",
            "inst_code": "DIT-PUNE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1000000.00"),
            "issue_date": date(2023, 8, 1),
            "maturity_date": date(2028, 8, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1000000.00"),
            "confirmed_issue": date(2023, 8, 1),
            "confirmed_mat": date(2028, 8, 1),
            "mismatch_fields": "",
            "docs": [("FDR_Certificate_884920.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Legitimate deposit whose reference number is cloned by another institution in different format.",
        },
        # ======================================================================
        # 2. WESTERN VALLEY COLLEGE OF ENGINEERING (WVCE-NASHIK) - 4 Records
        # ======================================================================
        {
            "ref": "DEMO/FDR/WDC/884920",  # Normalizes to 'demofdrwdc884920' identical to DIT's record!
            "inst_code": "WVCE-NASHIK",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1000000.00"),
            "issue_date": date(2023, 8, 1),
            "maturity_date": date(2028, 8, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1000000.00"),
            "confirmed_issue": date(2023, 8, 1),
            "confirmed_mat": date(2028, 8, 1),
            "mismatch_fields": "",
            "docs": [("WVCE_Scanned_Deposit_Slip.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "CRITICAL ANOMALY: Normalized duplicate reference collision across DIT Pune and WVCE Nashik.",
        },
        {
            "ref": "DEMO-FDR-WVCE-202",
            "inst_code": "WVCE-NASHIK",
            "bank": "National Valley Bank",
            "amount": Decimal("2000000.00"),
            "issue_date": date(2022, 1, 15),
            "maturity_date": date(2027, 1, 15),
            "status": "SUPERSEDED",
            "confirmed_bank": "National Valley Bank",
            "confirmed_amount": Decimal("2000000.00"),
            "confirmed_issue": date(2022, 1, 15),
            "confirmed_mat": date(2027, 1, 15),
            "mismatch_fields": "",
            "docs": [("Original_Damaged_Receipt_WVCE_202.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Original FDR certificate reported damaged in transit; replaced under regulatory protocol.",
        },
        {
            "ref": "DEMO-FDR-WVCE-203",
            "inst_code": "WVCE-NASHIK",
            "bank": "National Valley Bank",
            "amount": Decimal("2000000.00"),
            "issue_date": date(2022, 1, 15),
            "maturity_date": date(2027, 1, 15),
            "status": "ACTIVE",
            "confirmed_bank": "National Valley Bank",
            "confirmed_amount": Decimal("2000000.00"),
            "confirmed_issue": date(2022, 1, 15),
            "confirmed_mat": date(2027, 1, 15),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-WVCE-202",
            "lineage_rel": "REPLACEMENT",
            "docs": [
                ("Duplicate_Issued_Certificate_WVCE_203.pdf", "application/pdf"),
                ("Bank_Indemnity_Bond_WVCE_203.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": [],
            "summary": "Replacement successor: Replaces WVCE-202 with fresh bank security certificate.",
        },
        {
            "ref": "DEMO-FDR-WVCE-204",
            "inst_code": "WVCE-NASHIK",
            "bank": "National Valley Bank",
            "amount": Decimal("3500000.00"),
            "issue_date": date(2021, 11, 10),
            "maturity_date": date(2026, 11, 10),  # 12 days to maturity!
            "status": "ACTIVE",
            "confirmed_bank": "National Valley Bank",
            "confirmed_amount": Decimal("3500000.00"),
            "confirmed_issue": date(2021, 11, 10),
            "confirmed_mat": date(2026, 11, 10),
            "mismatch_fields": "",
            "docs": [("FDR_WVCE_204.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Due soon in 12 days: Approaching maturity deadline for technical program renewal.",
        },
        # ======================================================================
        # 3. SAHYADRI INSTITUTE OF APPLIED SCIENCES (SIAS-KOLHAPUR) - 4 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-SIAS-301",
            "inst_code": "SIAS-KOLHAPUR",
            "bank": "Pioneer Financial Bank",
            "amount": Decimal("1200000.00"),
            "issue_date": date(2024, 6, 30),
            "maturity_date": date(2029, 6, 30),
            "status": "DISCREPANCY",
            "confirmed_bank": "Pioneer Financial Bank",
            "confirmed_amount": Decimal("1200000.00"),
            "confirmed_issue": date(2024, 6, 30),
            "confirmed_mat": date(2027, 6, 30),  # Confirmed only 3 years instead of 5!
            "mismatch_fields": "maturity_date",
            "docs": [("Submitted_Deposit_SIAS_301.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Discrepancy: Submitted 5-year duration but bank confirmed 3-year term. Generates deficiency report.",
        },
        {
            "ref": "DEMO-FDR-SIAS-302",
            "inst_code": "SIAS-KOLHAPUR",
            "bank": "Pioneer Financial Bank",
            "amount": Decimal("1800000.00"),
            "issue_date": date(2021, 11, 20),
            "maturity_date": date(2026, 11, 20),  # 22 days to maturity!
            "status": "ACTIVE",
            "confirmed_bank": "Pioneer Financial Bank",
            "confirmed_amount": Decimal("1800000.00"),
            "confirmed_issue": date(2021, 11, 20),
            "confirmed_mat": date(2026, 11, 20),
            "mismatch_fields": "",
            "docs": [("FDR_Certificate_SIAS_302.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Upcoming maturity in 22 days: Flagged on dashboard upcoming deadlines schedule.",
        },
        {
            "ref": "DEMO-FDR-SIAS-303",
            "inst_code": "SIAS-KOLHAPUR",
            "bank": "Pioneer Financial Bank",
            "amount": Decimal("400000.00"),
            "issue_date": date(2020, 3, 1),
            "maturity_date": date(2023, 3, 1),  # 36 months, ₹4L
            "status": "MATURED",
            "confirmed_bank": "Pioneer Financial Bank",
            "confirmed_amount": Decimal("400000.00"),
            "confirmed_issue": date(2020, 3, 1),
            "confirmed_mat": date(2023, 3, 1),
            "mismatch_fields": "",
            "docs": [("Historic_Receipt_SIAS_303.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [
                "REG-AICTE-APH-2020:1.0.0:COMPLIANT",  # Compliant under 2020 baseline (min ₹3L, 36mo)
            ],
            "summary": "Regulation Replay Case: COMPLIANT under APH 2020, but flips to NON_COMPLIANT upon replay against APH 2025.",
        },
        {
            "ref": "DEMO-FDR-SIAS-304",
            "inst_code": "SIAS-KOLHAPUR",
            "bank": "Pioneer Financial Bank",
            "amount": Decimal("5000000.00"),
            "issue_date": date(2024, 2, 10),
            "maturity_date": date(2029, 2, 10),
            "status": "ACTIVE",
            "confirmed_bank": "Pioneer Financial Bank",
            "confirmed_amount": Decimal("5000000.00"),
            "confirmed_issue": date(2024, 2, 10),
            "confirmed_mat": date(2029, 2, 10),
            "mismatch_fields": "",
            "docs": [
                ("FDR_SIAS_304.pdf", "application/pdf"),
                ("Lien_Letter_SIAS_304.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2023:2.0.0:COMPLIANT"],
            "summary": "Clean large security deposit verified and compliant under all regulatory frameworks.",
        },
        # ======================================================================
        # 4. COASTAL TECHNICAL UNIVERSITY, GOA (CTU-GOA) - 4 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-CTU-401",
            "inst_code": "CTU-GOA",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("3000000.00"),
            "issue_date": date(2021, 8, 15),
            "maturity_date": date(2026, 8, 15),  # Matured 75 days ago!
            "status": "MATURED",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("3000000.00"),
            "confirmed_issue": date(2021, 8, 15),
            "confirmed_mat": date(2026, 8, 15),
            "mismatch_fields": "",
            "docs": [
                ("Original_FDR_Certificate_CTU_401.pdf", "application/pdf"),
                ("Bank_Clearance_Confirmation_CTU_401.pdf", "application/pdf"),
                ("Governing_Body_Release_Resolution.pdf", "application/pdf"),
            ],
            "rel_req": {
                "status": "PENDING",
                "requested_by": "institution4",
                "decided_by": None,
                "remarks": "Lock-in period of 5 years successfully completed. Requesting formal release of security deposit.",
            },
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Release Readiness Showcase: Fully satisfied prerequisite graph. Overall status READY_FOR_APPROVAL.",
        },
        {
            "ref": "DEMO-FDR-CTU-402",
            "inst_code": "CTU-GOA",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("1500000.00"),
            "issue_date": date(2021, 10, 15),
            "maturity_date": date(2026, 10, 15),  # 14 days overdue!
            "status": "MATURED",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("1500000.00"),
            "confirmed_issue": date(2021, 10, 15),
            "confirmed_mat": date(2026, 10, 15),
            "mismatch_fields": "",
            "docs": [("FDR_CTU_402.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Overdue maturity: Matured 14 days ago on 2026-10-15. Pending renewal or release submission.",
        },
        {
            "ref": "DEMO-FDR-CTU-403",
            "inst_code": "CTU-GOA",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("10000000.00"),  # ₹1 Crore
            "issue_date": date(2025, 1, 1),
            "maturity_date": date(2030, 1, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("10000000.00"),
            "confirmed_issue": date(2025, 1, 1),
            "confirmed_mat": date(2030, 1, 1),
            "mismatch_fields": "",
            "docs": [
                ("University_Endowment_FDR_CTU_403.pdf", "application/pdf"),
                ("Lien_Confirmation_CTU_403.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Flagship university campus establishment endowment FDR (₹1 Crore).",
        },
        {
            "ref": "DEMO-FDR-CTU-404",
            "inst_code": "CTU-GOA",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("2000000.00"),
            "issue_date": date(2024, 9, 1),
            "maturity_date": date(2029, 9, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("2000000.00"),
            "confirmed_issue": date(2024, 9, 1),
            "confirmed_mat": date(2029, 9, 1),
            "mismatch_fields": "",
            "docs": [("FDR_CTU_404.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Standard active security deposit for engineering programs.",
        },
        # ======================================================================
        # 5. CENTRAL INDIA COLLEGE OF TECHNOLOGY (CICT-NAGPUR) - 3 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-CICT-501",
            "inst_code": "CICT-NAGPUR",
            "bank": "Central Crest Bank",  # Submitted bank
            "amount": Decimal("2200000.00"),
            "issue_date": date(2021, 9, 1),
            "maturity_date": date(2026, 9, 1),  # Matured
            "status": "ACTIVE",
            "confirmed_bank": "National Valley Bank",  # Confirmed conflicting bank!
            "confirmed_amount": Decimal("2200000.00"),
            "confirmed_issue": date(2021, 9, 1),
            "confirmed_mat": date(2026, 9, 1),
            "mismatch_fields": "bank_name",
            "docs": [
                ("FDR_CICT_501.pdf", "application/pdf"),
                ("Bank_Letter_Conflicting.pdf", "application/pdf"),
            ],
            "rel_req": {
                "status": "PENDING",
                "requested_by": "institution5",
                "decided_by": None,
                "remarks": "Request for deposit release following completion of 5-year tenure.",
            },
            "snapshots": [],
            "summary": "Release Readiness Blocker: Has release request and completed term, but BLOCKED by active BANK_MISMATCH anomaly.",
        },
        {
            "ref": "DEMO-FDR-CICT-502",
            "inst_code": "CICT-NAGPUR",
            "bank": "Central Crest Bank",
            "amount": Decimal("1800000.00"),
            "issue_date": date(2023, 7, 1),
            "maturity_date": date(2028, 7, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",  # Mismatch
            "confirmed_amount": Decimal("1800000.00"),
            "confirmed_issue": date(2023, 7, 1),
            "confirmed_mat": date(2028, 7, 1),
            "mismatch_fields": "bank_name",
            "docs": [("FDR_CICT_502.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Integrity Network Investigation: Assigned to officer1 with status UNDER_REVIEW.",
        },
        {
            "ref": "DEMO-FDR-CICT-503",
            "inst_code": "CICT-NAGPUR",
            "bank": "Central Crest Bank",
            "amount": Decimal("4000000.00"),
            "issue_date": date(2024, 6, 15),
            "maturity_date": date(2029, 6, 15),
            "status": "ACTIVE",
            "confirmed_bank": "Central Crest Bank",
            "confirmed_amount": Decimal("4000000.00"),
            "confirmed_issue": date(2024, 6, 15),
            "confirmed_mat": date(2029, 6, 15),
            "mismatch_fields": "",
            "docs": [
                ("FDR_CICT_503.pdf", "application/pdf"),
                ("Lien_Letter_CICT_503.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2023:2.0.0:COMPLIANT"],
            "summary": "Clean baseline active security deposit.",
        },
        # ======================================================================
        # 6. RIVERBEND INSTITUTE OF ENGINEERING (RIE-INDORE) - 3 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-RIE-601",
            "inst_code": "RIE-INDORE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("1600000.00"),
            "issue_date": date(2021, 5, 15),
            "maturity_date": date(2026, 5, 15),  # Matured
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("1600000.00"),
            "confirmed_issue": date(2021, 5, 15),
            "confirmed_mat": date(2026, 5, 15),
            "mismatch_fields": "",
            "docs": [],  # ZERO documents uploaded!
            "rel_req": {
                "status": "PENDING",
                "requested_by": "institution6",
                "decided_by": None,
                "remarks": "Release requested after term maturity.",
            },
            "snapshots": [],
            "summary": "Release Readiness Blocker: Has release request and matured term, but BLOCKED by missing required documents.",
        },
        {
            "ref": "DEMO-FDR-RIE-602",
            "inst_code": "RIE-INDORE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2020, 1, 10),  # Precedes predecessor issue date 2022-06-10!
            "maturity_date": date(2025, 1, 10),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("2500000.00"),
            "confirmed_issue": date(2020, 1, 10),
            "confirmed_mat": date(2025, 1, 10),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-RIE-603",
            "lineage_rel": "RENEWAL",
            "docs": [("FDR_RIE_602.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Lineage Anomaly: Successor FDR has issue date (2020) preceding its predecessor (2022). Triggers date conflict.",
        },
        {
            "ref": "DEMO-FDR-RIE-603",
            "inst_code": "RIE-INDORE",
            "bank": "Western Deccan Cooperative Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2022, 6, 10),
            "maturity_date": date(2027, 6, 10),
            "status": "ACTIVE",
            "confirmed_bank": "Western Deccan Cooperative Bank",
            "confirmed_amount": Decimal("2500000.00"),
            "confirmed_issue": date(2022, 6, 10),
            "confirmed_mat": date(2027, 6, 10),
            "mismatch_fields": "",
            "docs": [("FDR_RIE_603.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Ancestor for RIE-602 involved in chronological lineage conflict anomaly.",
        },
        # ======================================================================
        # 7. HORIZON POLYTECHNIC INSTITUTE (HPI-AURANGABAD) - 3 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-HPI-701",
            "inst_code": "HPI-AURANGABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("3000000.00"),
            "issue_date": date(2023, 12, 31),
            "maturity_date": date(2028, 12, 31),  # Term not complete: 793 days remaining!
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("3000000.00"),
            "confirmed_issue": date(2023, 12, 31),
            "confirmed_mat": date(2028, 12, 31),
            "mismatch_fields": "",
            "docs": [
                ("FDR_HPI_701.pdf", "application/pdf"),
                ("Lien_Confirmation_HPI_701.pdf", "application/pdf"),
            ],
            "rel_req": {
                "status": "PENDING",
                "requested_by": "institution7",
                "decided_by": None,
                "remarks": "Premature withdrawal requested by institution prior to term maturity date.",
            },
            "snapshots": [],
            "summary": "Release Readiness Blocker: Premature release attempt. BLOCKED by PREREQ_MATURITY_ELIGIBILITY.",
        },
        {
            "ref": "DEMO-FDR-HPI-702",
            "inst_code": "HPI-AURANGABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("2800000.00"),
            "issue_date": date(2024, 1, 15),
            "maturity_date": date(2029, 1, 15),
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("2800000.00"),
            "confirmed_issue": date(2024, 1, 15),
            "confirmed_mat": date(2029, 1, 15),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-MCT-801",  # Points to Institution 8's FDR!
            "lineage_rel": "RENEWAL",
            "docs": [("FDR_HPI_702.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Cross-Institution Predecessor Anomaly: Predecessor belongs to Meridian College of Technology.",
        },
        {
            "ref": "DEMO-FDR-HPI-703",
            "inst_code": "HPI-AURANGABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("2200000.00"),
            "issue_date": date(2024, 5, 1),
            "maturity_date": date(2029, 5, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("2200000.00"),
            "confirmed_issue": date(2024, 5, 1),
            "confirmed_mat": date(2029, 5, 1),
            "mismatch_fields": "",
            "docs": [("FDR_HPI_703.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Invalid Predecessor Anomaly: References orphaned non-existent predecessor ID 99999.",
        },
        # ======================================================================
        # 8. MERIDIAN COLLEGE OF TECHNOLOGY (MCT-BENGALURU) - 3 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-MCT-801",
            "inst_code": "MCT-BENGALURU",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("3000000.00"),
            "issue_date": date(2022, 1, 15),
            "maturity_date": date(2027, 1, 15),
            "status": "ACTIVE",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("3000000.00"),
            "confirmed_issue": date(2022, 1, 15),
            "confirmed_mat": date(2027, 1, 15),
            "mismatch_fields": "",
            "docs": [("FDR_MCT_801.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Legitimate active deposit targeted by cross-institution predecessor reference.",
        },
        {
            "ref": "DEMO-FDR-MCT-802",
            "inst_code": "MCT-BENGALURU",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("2000000.00"),
            "issue_date": date(2023, 1, 10),
            "maturity_date": date(2028, 1, 10),  # 60 months, ₹20L
            "status": "ACTIVE",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("2000000.00"),
            "confirmed_issue": date(2023, 1, 10),
            "confirmed_mat": date(2028, 1, 10),
            "mismatch_fields": "",
            "docs": [
                ("FDR_Receipt_MCT_802.pdf", "application/pdf"),
                ("Bank_Lien_Confirmation_MCT_802.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": [
                "REG-AICTE-APH-2023:2.0.0:COMPLIANT",  # COMPLIANT under 2023
                # Remains COMPLIANT under 2025 replay!
            ],
            "summary": "Regulation Replay Exemplar: COMPLIANT under APH 2023, remains COMPLIANT under APH 2025.",
        },
        {
            "ref": "DEMO-FDR-MCT-803",
            "inst_code": "MCT-BENGALURU",
            "bank": "Meridian Commercial Bank",
            "amount": Decimal("6000000.00"),
            "issue_date": date(2025, 3, 1),
            "maturity_date": date(2030, 3, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Meridian Commercial Bank",
            "confirmed_amount": Decimal("6000000.00"),
            "confirmed_issue": date(2025, 3, 1),
            "confirmed_mat": date(2030, 3, 1),
            "mismatch_fields": "",
            "docs": [("FDR_MCT_803.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Large capital security deposit active through 2030.",
        },
        # ======================================================================
        # 9. NORTHSTAR INSTITUTE OF ENGINEERING (NIE-HYDERABAD) - 4 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-NIE-901",
            "inst_code": "NIE-HYDERABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2024, 4, 10),
            "maturity_date": date(2029, 4, 10),
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("2500000.00"),
            "confirmed_issue": date(2024, 4, 10),
            "confirmed_mat": date(2029, 4, 10),
            "mismatch_fields": "",
            "docs": [("FDR_NIE_901.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "First active deposit in suspect identical pair (₹25L, Horizon Urban Bank).",
        },
        {
            "ref": "DEMO-FDR-NIE-902",
            "inst_code": "NIE-HYDERABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2024, 4, 12),
            "maturity_date": date(2029, 4, 15),  # 5 days apart, same bank & amount!
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("2500000.00"),
            "confirmed_issue": date(2024, 4, 12),
            "confirmed_mat": date(2029, 4, 15),
            "mismatch_fields": "",
            "docs": [("FDR_NIE_902.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Suspect multiple active deposit: Clones bank, amount, and maturity window within 5 days.",
        },
        {
            "ref": "DEMO-FDR-NIE-903",
            "inst_code": "NIE-HYDERABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("3000000.00"),
            "issue_date": date(2021, 1, 1),
            "maturity_date": date(2026, 1, 1),
            "status": "RENEWED",  # Already renewed!
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("3000000.00"),
            "confirmed_issue": date(2021, 1, 1),
            "confirmed_mat": date(2026, 1, 1),
            "mismatch_fields": "",
            "docs": [("FDR_NIE_903.pdf", "application/pdf")],
            "rel_req": {
                "status": "PENDING",
                "requested_by": "institution9",
                "decided_by": None,
                "remarks": "Release requested on historical deposit voucher.",
            },
            "snapshots": [],
            "summary": "Integrity Anomaly: Release requested on FDR that has already been superseded by renewal.",
        },
        {
            "ref": "DEMO-FDR-NIE-904",
            "inst_code": "NIE-HYDERABAD",
            "bank": "Horizon Urban Bank",
            "amount": Decimal("3500000.00"),
            "issue_date": date(2026, 1, 1),
            "maturity_date": date(2031, 1, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Horizon Urban Bank",
            "confirmed_amount": Decimal("3500000.00"),
            "confirmed_issue": date(2026, 1, 1),
            "confirmed_mat": date(2031, 1, 1),
            "mismatch_fields": "",
            "pred_ref": "DEMO-FDR-NIE-903",
            "lineage_rel": "RENEWAL",
            "docs": [
                ("FDR_NIE_904.pdf", "application/pdf"),
                ("Renewal_Advice_NIE_904.pdf", "application/pdf"),
            ],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Active renewal successor to NIE-903.",
        },
        # ======================================================================
        # 10. GREENFIELD TECHNICAL COLLEGE (GTC-BHOPAL) - 3 Records
        # ======================================================================
        {
            "ref": "DEMO-FDR-GTC-1001",
            "inst_code": "GTC-BHOPAL",
            "bank": "Central Crest Bank",
            "amount": Decimal("1500000.00"),
            "issue_date": date(2020, 1, 1),
            "maturity_date": date(2025, 1, 1),
            "status": "RELEASED",  # Complete lifecycle released!
            "confirmed_bank": "Central Crest Bank",
            "confirmed_amount": Decimal("1500000.00"),
            "confirmed_issue": date(2020, 1, 1),
            "confirmed_mat": date(2025, 1, 1),
            "mismatch_fields": "",
            "docs": [
                ("Original_Receipt_GTC_1001.pdf", "application/pdf"),
                ("Bank_Lien_Release_Letter.pdf", "application/pdf"),
            ],
            "rel_req": {
                "status": "APPROVED",
                "requested_by": "institution10",
                "decided_by": "approver1",
                "remarks": "Security deposit released following fulfillment of mandatory lock-in period and dual bank confirmation.",
            },
            "snapshots": ["REG-AICTE-APH-2020:1.0.0:COMPLIANT"],
            "summary": "Complete lifecycle showcase: Full term completed, approved by approver1, deposit closed.",
        },
        {
            "ref": "DEMO-FDR-GTC-1002",
            "inst_code": "GTC-BHOPAL",
            "bank": "Central Crest Bank",
            "amount": Decimal("5000000.00"),
            "issue_date": date(2025, 7, 1),
            "maturity_date": date(2030, 7, 1),
            "status": "ACTIVE",
            "confirmed_bank": "Central Crest Bank",
            "confirmed_amount": Decimal("5000000.00"),
            "confirmed_issue": date(2025, 7, 1),
            "confirmed_mat": date(2030, 7, 1),
            "mismatch_fields": "",
            "docs": [("FDR_GTC_1002.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": ["REG-AICTE-APH-2025:2.5.0-DEMO:COMPLIANT"],
            "summary": "Clean active security deposit for engineering polytechnic.",
        },
        {
            "ref": "DEMO-FDR-GTC-1003",
            "inst_code": "GTC-BHOPAL",
            "bank": "Central Crest Bank",
            "amount": Decimal("2500000.00"),
            "issue_date": date(2026, 10, 1),
            "maturity_date": date(2031, 10, 1),
            "status": "SUBMITTED",  # Awaiting initial scrutiny!
            "confirmed_bank": None,
            "confirmed_amount": None,
            "confirmed_issue": None,
            "confirmed_mat": None,
            "mismatch_fields": "",
            "docs": [("Submitted_Certificate_GTC_1003.pdf", "application/pdf")],
            "rel_req": None,
            "snapshots": [],
            "summary": "Freshly submitted deposit awaiting regulatory officer scrutiny and bank confirmation.",
        },
    ]

    # STEP 1: Insert or update all deposits
    for spec in DEPOSITS_SPEC:
        ref = spec["ref"]
        inst = inst_map[spec["inst_code"]]
        dep = db.scalar(select(Deposit).where(Deposit.reference_hash == fdr_number_hash(ref)))
        if not dep:
            dep = Deposit(
                reference_no=ref,
                institution_id=inst.id,
                bank_name=spec["bank"],
                amount=spec["amount"],
                issue_date=spec["issue_date"],
                maturity_date=spec["maturity_date"],
                status=spec["status"],
                confirmed_bank_name=spec.get("confirmed_bank"),
                confirmed_amount=spec.get("confirmed_amount"),
                confirmed_issue_date=spec.get("confirmed_issue"),
                confirmed_maturity_date=spec.get("confirmed_mat"),
                mismatch_fields=spec.get("mismatch_fields", ""),
            )
            db.add(dep)
            db.flush()
        else:
            dep.institution_id = inst.id
            dep.bank_name = spec["bank"]
            dep.amount = spec["amount"]
            dep.issue_date = spec["issue_date"]
            dep.maturity_date = spec["maturity_date"]
            dep.status = spec["status"]
            dep.confirmed_bank_name = spec.get("confirmed_bank")
            dep.confirmed_amount = spec.get("confirmed_amount")
            dep.confirmed_issue_date = spec.get("confirmed_issue")
            dep.confirmed_maturity_date = spec.get("confirmed_mat")
            dep.mismatch_fields = spec.get("mismatch_fields", "")
        created_deposits[ref] = dep

    db.commit()

    # Special handling for HPI-703: Invalid predecessor ID 99999
    hpi_703 = created_deposits.get("DEMO-FDR-HPI-703")
    if hpi_703:
        hpi_703.previous_deposit_id = 99999
        db.flush()

    # STEP 2: Seed Documents and local files
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        doc_specs = spec.get("docs", [])
        for fname, ctype in doc_specs:
            existing_doc = db.scalar(
                select(Document).where(Document.deposit_id == dep.id, Document.filename == fname)
            )
            if not existing_doc:
                storage_key = f"demo_{dep.id}_{fname.replace(' ', '_')}"
                doc = Document(
                    deposit_id=dep.id,
                    filename=fname,
                    content_type=ctype,
                    size_bytes=len(SAMPLE_PDF_HEADER),
                    storage_key=storage_key,
                    uploaded_by="system",
                    uploaded_at=_ts(spec["issue_date"]),
                )
                db.add(doc)
                # Also save physical dummy file to UPLOAD_DIR
                try:
                    storage_save(storage_key, SAMPLE_PDF_HEADER)
                except Exception as e:
                    log.warning(f"Could not write demo file {storage_key}: {e}")
    db.commit()

    # STEP 3: Seed Lineage Relations and Predecessors
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        pred_ref = spec.get("pred_ref")
        if pred_ref and pred_ref in created_deposits:
            pred_dep = created_deposits[pred_ref]
            dep.previous_deposit_id = pred_dep.id
            rel_type = spec.get("lineage_rel", "RENEWAL")
            try:
                trace_service.add_lineage_relation(
                    db=db,
                    source_id=pred_dep.id,
                    target_id=dep.id,
                    relation_type=rel_type,
                    actor="system",
                    metadata={"source": "demo_dataset", "demo_tag": DEMO_TAG},
                    created_at=_ts(dep.issue_date),
                )
            except ValueError:
                pass

    db.commit()

    # STEP 4: Seed Release Requests
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        req_spec = spec.get("rel_req")
        if req_spec:
            existing_req = db.scalar(
                select(ReleaseRequest).where(ReleaseRequest.deposit_id == dep.id)
            )
            if not existing_req:
                rel = ReleaseRequest(
                    deposit_id=dep.id,
                    status=req_spec["status"],
                    status_before="ACTIVE" if dep.status != "RELEASED" else "MATURED",
                    requested_by=req_spec["requested_by"],
                    decided_by=req_spec.get("decided_by"),
                    remarks=f"{req_spec['remarks']} [{DEMO_TAG}]",
                )
                db.add(rel)
                db.flush()
            else:
                existing_req.status = req_spec["status"]
                existing_req.requested_by = req_spec["requested_by"]
                existing_req.decided_by = req_spec.get("decided_by")
                existing_req.remarks = f"{req_spec['remarks']} [{DEMO_TAG}]"
    db.commit()

    # STEP 5: Seed Hash-Chained Timeline Events for Every Deposit
    # Clean previous demo lifecycle events for our demo deposits to ensure pure cryptographic chain
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        events = db.scalars(
            select(FDRLifecycleEvent).where(FDRLifecycleEvent.deposit_id == dep.id)
        ).all()
        if not events:
            # Build chronological sequence of realistic events
            ev_list = []
            issue_d = dep.issue_date

            # Event 1: Deposit Submitted
            ev_list.append({
                "type": "DEPOSIT_SUBMITTED",
                "actor": "institution1",
                "role": "INSTITUTION_USER",
                "summary": f"Initial deposit record submitted for ₹{float(dep.amount):,.2f}",
                "details": {"reference_no": dep.reference_no, "bank_name": dep.bank_name, "amount": float(dep.amount), "demo_tag": DEMO_TAG},
                "ts": _ts(issue_d, 9, 30),
            })

            # Event 2: Documents Uploaded
            for fname, _ in spec.get("docs", []):
                ev_list.append({
                    "type": "DOCUMENT_UPLOADED",
                    "actor": "institution1",
                    "role": "INSTITUTION_USER",
                    "summary": f"Uploaded document: {fname}",
                    "details": {"filename": fname, "demo_tag": DEMO_TAG},
                    "ts": _ts(issue_d, 10, 15),
                })

            # Event 3: Bank Confirmation / Scrutiny
            if dep.status in ["ACTIVE", "MATURED", "RELEASED", "RENEWED"]:
                ev_list.append({
                    "type": "BANK_CONFIRMATION_RECEIVED",
                    "actor": "officer1",
                    "role": "REGULATOR_OFFICER",
                    "summary": f"Bank confirmation verified: {dep.bank_name} records match submitted parameters",
                    "details": {"confirmed_bank": dep.confirmed_bank_name, "confirmed_amount": float(dep.confirmed_amount or dep.amount), "demo_tag": DEMO_TAG},
                    "ts": _ts(issue_d + timedelta(days=5), 14, 0),
                })
            elif dep.status == "DISCREPANCY":
                ev_list.append({
                    "type": "DISCREPANCY_FLAGGED",
                    "actor": "officer1",
                    "role": "REGULATOR_OFFICER",
                    "summary": f"Scrutiny discrepancy detected in fields: {dep.mismatch_fields}",
                    "details": {"mismatches": dep.mismatch_fields, "demo_tag": DEMO_TAG},
                    "ts": _ts(issue_d + timedelta(days=3), 11, 45),
                })

            # Event 4: Release Request
            if spec.get("rel_req"):
                r_spec = spec["rel_req"]
                req_ts = _ts(dep.maturity_date, 11, 0) if dep.maturity_date <= today else _ts(today - timedelta(days=3), 11, 0)
                ev_list.append({
                    "type": "RELEASE_REQUESTED",
                    "actor": r_spec["requested_by"],
                    "role": "INSTITUTION_USER",
                    "summary": "Formal release application submitted with governing body justification",
                    "details": {"remarks": r_spec["remarks"], "demo_tag": DEMO_TAG},
                    "ts": req_ts,
                })
                if r_spec["status"] == "APPROVED":
                    ev_list.append({
                        "type": "RELEASE_APPROVED",
                        "actor": r_spec["decided_by"] or "approver1",
                        "role": "APPROVING_AUTHORITY",
                        "summary": "Release approved by Approving Authority. Authorization issued to bank.",
                        "details": {"decided_by": r_spec["decided_by"], "demo_tag": DEMO_TAG},
                        "ts": req_ts + timedelta(days=2),
                    })

            # Append all events using record_lifecycle_event so hash chains are cryptographically calculated
            for ev in ev_list:
                trace_service.record_lifecycle_event(
                    db=db,
                    deposit_id=dep.id,
                    event_type=ev["type"],
                    actor=ev["actor"],
                    actor_role=ev["role"],
                    summary=ev["summary"],
                    details=ev["details"],
                    created_at=ev["ts"],
                )
    db.commit()

    # STEP 6: Seed Historical Assessment Snapshots for Regulation Replay
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        snapshot_specs = spec.get("snapshots", [])
        for snap_str in snapshot_specs:
            parts = snap_str.split(":")
            rule_code, rule_ver, expected_result = parts[0], parts[1], parts[2]
            rule = db.scalar(
                select(RegulationRule).where(
                    RegulationRule.rule_code == rule_code,
                    RegulationRule.version == rule_ver,
                )
            )
            if rule:
                existing_snap = db.scalar(
                    select(AssessmentSnapshot).where(
                        AssessmentSnapshot.deposit_id == dep.id,
                        AssessmentSnapshot.rule_id == rule.id,
                    )
                )
                if not existing_snap:
                    # Evaluate spec
                    rule_spec = json.loads(rule.rule_spec_json)
                    docs = db.scalars(select(Document).where(Document.deposit_id == dep.id)).all()
                    dep_data = {
                        "amount": float(dep.amount),
                        "issue_date": dep.issue_date.isoformat(),
                        "maturity_date": dep.maturity_date.isoformat(),
                        "bank_name": dep.bank_name,
                        "mismatch_fields": dep.mismatch_fields,
                        "uploaded_documents": [d.filename for d in docs],
                    }
                    eval_out = regulation_service.evaluate_rule_spec(rule_spec, dep_data)
                    snap = AssessmentSnapshot(
                        deposit_id=dep.id,
                        rule_id=rule.id,
                        rule_code=rule.rule_code,
                        rule_version=rule.version,
                        assessment_type="DEPOSIT_COMPLIANCE",
                        is_replay=False,
                        input_snapshot_json=json.dumps(dep_data, sort_keys=True),
                        evaluation_result=expected_result,
                        conditions_evaluated_json=json.dumps(eval_out["conditions"], sort_keys=True),
                        assessed_by="officer1",
                        assessed_at=_ts(dep.issue_date + timedelta(days=7), 16, 0),
                    )
                    db.add(snap)
    db.commit()

    # STEP 7: Run Full Cross-Record Integrity Scan to Generate Network Findings
    integrity_scan_res = integrity_service.run_integrity_scan(db)
    db.commit()

    # STEP 8: Seed Workflow Investigation Actions on Selected Findings
    findings = db.scalars(select(IntegrityFinding)).all()
    for f in findings:
        if "BANK_MISMATCH" in f.finding_code:
            # Add an investigation review action to demonstrate reviewer workflow
            existing_actions = db.scalars(
                select(IntegrityFindingAction).where(IntegrityFindingAction.finding_id == f.id)
            ).all()
            if not existing_actions:
                f.status = "UNDER_REVIEW"
                f.assignee = "officer1"
                act = IntegrityFindingAction(
                    finding_id=f.id,
                    action="STATUS_CHANGE",
                    actor="officer1",
                    actor_role="REGULATOR_OFFICER",
                    notes=f"Contacted branch manager regarding bank name variance. Official branch lien letter requested. [{DEMO_TAG}]",
                    created_at=utcnow(),
                )
                db.add(act)
    db.commit()

    # STEP 9: Compute and Pre-Evaluate Release Readiness Snapshots
    for spec in DEPOSITS_SPEC:
        dep = created_deposits[spec["ref"]]
        if spec.get("rel_req"):
            try:
                readiness_service.evaluate_release_readiness(db, dep.id, save_snapshot=True)
            except Exception as e:
                log.warning(f"Could not pre-evaluate readiness for FDR #{dep.id}: {e}")
    db.commit()

    total_deposits = db.query(Deposit).count()
    total_insts = db.query(Institution).count()
    total_findings = db.query(IntegrityFinding).count()
    total_events = db.query(FDRLifecycleEvent).count()
    total_snapshots = db.query(AssessmentSnapshot).count()
    total_rules = db.query(RegulationRule).count()
    total_relations = db.query(FDRLineageRelation).count()
    total_releases = db.query(ReleaseRequest).count()

    return {
        "status": "success",
        "institutions_count": total_insts,
        "deposits_count": total_deposits,
        "integrity_findings_count": total_findings,
        "lifecycle_events_count": total_events,
        "assessment_snapshots_count": total_snapshots,
        "regulation_rules_count": total_rules,
        "lineage_relations_count": total_relations,
        "release_requests_count": total_releases,
        "integrity_scan_result": integrity_scan_res,
    }


if __name__ == "__main__":
    from .db import SessionLocal

    with SessionLocal() as session:
        result = seed_demonstration_dataset(session)
        print("Demo Dataset Seed Summary:")
        for k, v in result.items():
            print(f"  {k}: {v}")
