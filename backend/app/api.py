import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import os

from . import extract, reports, storage
from .auth import Actor, get_actor, require
from .db import get_db
from .lifecycle import REMINDED, STATUSES, TRACKED, mismatched_fields
from .models import AuditLog, Deposit, Document, EmailLog, Institution, JobRun, Notification, ReleaseRequest, SmsLog, utcnow
from .scheduler import run_daily_check, today_ist
from .services import deadline_service, deficiency_service, trace_service
from .schemas import (
    AuditOut,
    CalendarEvent,
    DeadlinesResponse,
    DeficiencyReportGenerateIn,
    DeficiencyReportPreview,
    DepositCreate,
    DepositOut,
    DepositPage,
    DocumentOut,
    InstitutionCreate,
    InstitutionOut,
    NotificationOut,
    ReleaseDecision,
    ReleaseOut,
    RenewIn,
    VerifyIn,
)

router = APIRouter()

RENEWABLE = {"VERIFIED", "ACTIVE", "EXPIRING", "MATURED"}
RELEASABLE = {"ACTIVE", "EXPIRING", "MATURED"}
VERIFIABLE = {"SUBMITTED", "DISCREPANCY"}

ALLOWED_UPLOADS = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# ---- Scope: institution users only see their own institution --------------


def in_scope(actor: Actor, dep: Deposit) -> bool:
    return actor.role != "INSTITUTION_USER" or dep.institution_id == actor.institution_id


def scope_deposits(query, actor: Actor):
    if actor.role == "INSTITUTION_USER":
        return query.where(Deposit.institution_id == actor.institution_id)
    return query


# ---- Helpers --------------------------------------------------------------


def audit(db: Session, entity: str, entity_id: int, action: str, actor: str, detail: str = "") -> None:
    db.add(AuditLog(entity=entity, entity_id=entity_id, action=action, actor=actor, detail=detail))


def get_deposit_or_404(db: Session, deposit_id: int, actor: Actor) -> Deposit:
    dep = db.get(Deposit, deposit_id)
    # Same 404 for "missing" and "another institution's", so IDs cannot be probed.
    if dep is None or not in_scope(actor, dep):
        raise HTTPException(status_code=404, detail="Deposit not found")
    return dep


def ensure_reference_free(db: Session, reference_no: str) -> None:
    if db.scalar(select(Deposit.id).where(Deposit.reference_no == reference_no)) is not None:
        raise HTTPException(status_code=409, detail=f"Reference {reference_no} already exists")


# ---- Institutions ---------------------------------------------------------


@router.post("/institutions", status_code=201, response_model=InstitutionOut)
def create_institution(body: InstitutionCreate, db: Session = Depends(get_db), actor: Actor = Depends(require())):
    if db.scalar(select(Institution.id).where(Institution.code == body.code)) is not None:
        raise HTTPException(status_code=409, detail="Institution code already exists")
    inst = Institution(name=body.name, code=body.code)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    query = select(Institution).order_by(Institution.id)
    if actor.role == "INSTITUTION_USER":
        query = query.where(Institution.id == actor.institution_id)
    return db.scalars(query).all()


# ---- Deposits -------------------------------------------------------------


@router.post("/deposits", status_code=201, response_model=DepositOut)
def create_deposit(
    body: DepositCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER")),
):
    if actor.role == "INSTITUTION_USER" and body.institution_id != actor.institution_id:
        raise HTTPException(status_code=403, detail="You can only add FDRs for your own institution")
    if db.get(Institution, body.institution_id) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    ensure_reference_free(db, body.reference_no)
    dep = Deposit(**body.model_dump(), status="SUBMITTED")
    db.add(dep)
    db.flush()
    audit(db, "deposit", dep.id, "CREATED", actor.name, f"ref {dep.reference_no}, amount {dep.amount}")
    trace_service.record_lifecycle_event(
        db,
        dep.id,
        "CREATED_SUBMITTED",
        actor.name,
        f"FDR registered: Ref {dep.reference_no}, Amount ₹{dep.amount:,.2f}",
        {"bank": dep.bank_name, "issue_date": str(dep.issue_date), "maturity_date": str(dep.maturity_date)},
        actor.role,
    )
    db.commit()
    db.refresh(dep)
    return dep


@router.get("/deposits", response_model=DepositPage)
def list_deposits(
    status: Optional[str] = None,
    group: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    query = scope_deposits(select(Deposit), actor)
    if status:
        query = query.where(Deposit.status == status)
    if group:
        if group not in reports.GROUPS:
            raise HTTPException(status_code=400, detail=f"Unknown group {group}")
        statuses = reports.GROUPS[group]
        if statuses is not None:
            query = query.where(Deposit.status.in_(statuses))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Deposit.id).offset((page - 1) * page_size).limit(page_size)).all()
    return DepositPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/deposits/{deposit_id}", response_model=DepositOut)
def get_deposit(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    return get_deposit_or_404(db, deposit_id, actor)


@router.get("/deposits/{deposit_id}/history", response_model=list[AuditOut])
def deposit_history(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    get_deposit_or_404(db, deposit_id, actor)
    return db.scalars(
        select(AuditLog).where(AuditLog.entity == "deposit", AuditLog.entity_id == deposit_id).order_by(AuditLog.id)
    ).all()


@router.post("/deposits/{deposit_id}/verify", response_model=DepositOut)
def verify_deposit(
    deposit_id: int,
    body: VerifyIn,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER")),
):
    dep = get_deposit_or_404(db, deposit_id, actor)
    if dep.status not in VERIFIABLE:
        raise HTTPException(status_code=409, detail=f"Cannot verify a deposit in status {dep.status}")

    dep.confirmed_reference_no = body.confirmed_reference_no
    dep.confirmed_bank_name = body.confirmed_bank_name
    dep.confirmed_amount = body.confirmed_amount
    dep.confirmed_issue_date = body.confirmed_issue_date
    dep.confirmed_maturity_date = body.confirmed_maturity_date

    mismatches = mismatched_fields(dep)
    dep.mismatch_fields = ",".join(mismatches)
    dep.status = "DISCREPANCY" if mismatches else "VERIFIED"

    detail = f"mismatched: {', '.join(mismatches) or 'none'}. {body.observations}".strip()
    audit(db, "deposit", dep.id, "DISCREPANCY_FLAGGED" if mismatches else "VERIFIED", actor.name, detail)
    trace_service.record_lifecycle_event(
        db,
        dep.id,
        "DISCREPANCY_DETECTED" if mismatches else "VERIFICATION_STATUS_CHANGED",
        actor.name,
        f"Verification completed: status is now {dep.status}",
        {"mismatches": mismatches, "observations": body.observations},
        actor.role,
    )
    db.commit()
    db.refresh(dep)
    return dep


@router.post("/deposits/{deposit_id}/renew", status_code=201, response_model=DepositOut)
def renew_deposit(
    deposit_id: int,
    body: RenewIn,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER")),
):
    old = get_deposit_or_404(db, deposit_id, actor)
    if old.status not in RENEWABLE:
        raise HTTPException(status_code=409, detail=f"Cannot renew a deposit in status {old.status}")
    if body.institution_id != old.institution_id:
        raise HTTPException(status_code=400, detail="Renewal must belong to the same institution")
    ensure_reference_free(db, body.reference_no)

    new = Deposit(**body.model_dump(), status="SUBMITTED", previous_deposit_id=old.id)
    db.add(new)
    db.flush()
    old.status = "RENEWED"
    audit(db, "deposit", old.id, "RENEWED", actor.name, f"replaced by {new.reference_no}")
    audit(db, "deposit", new.id, "CREATED", actor.name, f"renewal of {old.reference_no}")
    trace_service.record_lifecycle_event(
        db,
        old.id,
        "SUPERSEDED_BY_RENEWAL",
        actor.name,
        f"FDR renewed/replaced by successor FDR #{new.id} ({new.reference_no})",
        {"new_id": new.id, "new_ref": new.reference_no},
        actor.role,
    )
    trace_service.record_lifecycle_event(
        db,
        new.id,
        "RENEWAL_RECORDED",
        actor.name,
        f"FDR created as renewal of predecessor FDR #{old.id} ({old.reference_no})",
        {"old_id": old.id, "old_ref": old.reference_no},
        actor.role,
    )
    try:
        trace_service.add_lineage_relation(
            db,
            old.id,
            new.id,
            "RENEWAL",
            actor.name,
            {"renewal_amount": float(new.amount)},
        )
    except Exception:
        pass
    db.commit()
    db.refresh(new)
    return new


# ---- Reading documents and suggesting fields ------------------------------


def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    ext_known = file.content_type in ALLOWED_UPLOADS
    if not ext_known:
        raise HTTPException(status_code=415, detail="Only PDF, PNG and JPEG files are allowed")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")
    return data, file.content_type or "application/octet-stream"


@router.post("/extract/fdr")
def extract_fdr_fields(
    file: UploadFile = File(...),
    actor: Actor = Depends(require("INSTITUTION_USER", "REGULATOR_OFFICER")),
):
    """Suggests FDR fields from an uploaded file. Nothing is saved; the user confirms the values."""
    data, content_type = _read_upload(file)
    return extract.extract_fdr(data, content_type)


@router.post("/deposits/{deposit_id}/documents", status_code=201, response_model=DocumentOut)
def upload_document(
    deposit_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER", "REGULATOR_OFFICER")),
):
    dep = get_deposit_or_404(db, deposit_id, actor)
    data, content_type = _read_upload(file)
    key = f"{uuid.uuid4().hex}{ALLOWED_UPLOADS[content_type]}"
    storage.save(key, data)
    doc = Document(
        deposit_id=dep.id,
        filename=Path(file.filename or "upload").name[:255],
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
        uploaded_by=actor.name,
        uploaded_at=utcnow(),
    )
    db.add(doc)
    db.flush()
    audit(db, "deposit", dep.id, "DOCUMENT_UPLOADED", actor.name, doc.filename)
    trace_service.record_lifecycle_event(
        db,
        dep.id,
        "DOCUMENT_UPLOADED",
        actor.name,
        f"Document uploaded: {doc.filename}",
        {"document_id": doc.id, "size_bytes": doc.size_bytes, "content_type": doc.content_type},
        actor.role,
    )
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/deposits/{deposit_id}/documents", response_model=list[DocumentOut])
def list_documents(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    get_deposit_or_404(db, deposit_id, actor)
    return db.scalars(select(Document).where(Document.deposit_id == deposit_id).order_by(Document.id)).all()


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    get_deposit_or_404(db, doc.deposit_id, actor)
    content = storage.read(doc.storage_key)
    if content is None:
        raise HTTPException(status_code=404, detail="File missing from storage")
    safe_name = doc.filename.replace('"', "")
    return Response(
        content=content,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ---- Release / refund -----------------------------------------------------


@router.post("/deposits/{deposit_id}/release", status_code=201, response_model=ReleaseOut)
def request_release(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER")),
):
    dep = get_deposit_or_404(db, deposit_id, actor)
    if dep.status not in RELEASABLE:
        raise HTTPException(status_code=409, detail=f"Cannot request release for status {dep.status}")
    pending = db.scalar(
        select(ReleaseRequest.id).where(ReleaseRequest.deposit_id == dep.id, ReleaseRequest.status == "PENDING")
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="A release request is already pending")

    rr = ReleaseRequest(deposit_id=dep.id, status="PENDING", status_before=dep.status, requested_by=actor.name, remarks="")
    db.add(rr)
    dep.status = "RELEASE_REQUESTED"
    db.flush()
    audit(db, "deposit", dep.id, "RELEASE_REQUESTED", actor.name, f"request {rr.id}")
    trace_service.record_lifecycle_event(
        db,
        dep.id,
        "RELEASE_REQUESTED",
        actor.name,
        f"Release request #{rr.id} submitted by {actor.name}",
        {"release_request_id": rr.id},
        actor.role,
    )
    db.commit()
    db.refresh(rr)
    return rr


@router.get("/release-requests", response_model=list[ReleaseOut])
def list_release_requests(
    status: str = Query("PENDING"),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    query = (
        select(ReleaseRequest)
        .join(Deposit, Deposit.id == ReleaseRequest.deposit_id)
        .where(ReleaseRequest.status == status)
    )
    if actor.role == "INSTITUTION_USER":
        query = query.where(Deposit.institution_id == actor.institution_id)
    return db.scalars(query.order_by(ReleaseRequest.id)).all()


@router.patch("/release-requests/{request_id}", response_model=ReleaseOut)
def decide_release(
    request_id: int,
    body: ReleaseDecision,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("APPROVING_AUTHORITY")),
):
    rr = db.get(ReleaseRequest, request_id)
    if rr is None:
        raise HTTPException(status_code=404, detail="Release request not found")
    if rr.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Release request already {rr.status}")

    dep = db.get(Deposit, rr.deposit_id)
    if body.approve:
        rr.status = "APPROVED"
        dep.status = "RELEASED"
        action = "RELEASE_APPROVED"
    else:
        rr.status = "REJECTED"
        dep.status = rr.status_before
        action = "RELEASE_REJECTED"

    rr.decided_by = actor.name
    rr.remarks = body.remarks
    audit(db, "deposit", dep.id, action, actor.name, body.remarks)
    trace_service.record_lifecycle_event(
        db,
        dep.id,
        "RELEASE_APPROVED" if body.approve else "RELEASE_REJECTED",
        actor.name,
        f"Release decision: {'Approved' if body.approve else 'Rejected'}. Remarks: {body.remarks}",
        {"approve": body.approve, "remarks": body.remarks},
        actor.role,
    )
    db.commit()
    db.refresh(rr)
    return rr


# ---- Notifications --------------------------------------------------------


def _notification_query(actor: Actor):
    query = select(Notification).join(Deposit, Deposit.id == Notification.deposit_id)
    if actor.role != "ADMIN":
        query = query.where(Notification.role == actor.role)
    if actor.role == "INSTITUTION_USER":
        query = query.where(Deposit.institution_id == actor.institution_id)
    return query


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    return db.scalars(_notification_query(actor).order_by(Notification.id.desc()).limit(100)).all()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    n = db.scalar(_notification_query(actor).where(Notification.id == notification_id))
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


@router.get("/admin/emails")
def list_email_log(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require()),
):
    rows = db.scalars(select(EmailLog).order_by(EmailLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "to": r.to_address,
            "subject": r.subject,
            "status": r.status,
            "error": r.error,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/admin/sms")
def list_sms_log(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require()),
):
    rows = db.scalars(select(SmsLog).order_by(SmsLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            # Masked so the admin log does not expose full phone numbers.
            "to": f"{r.to_number[:4]}XXXXXX{r.to_number[-2:]}",
            "message": r.message.replace("|", " "),
            "status": r.status,
            "error": r.error,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ---- Calendar, dashboard, reports, jobs -----------------------------------


@router.get("/calendar", response_model=list[CalendarEvent])
def calendar(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    if end < start:
        raise HTTPException(status_code=400, detail="end must be on or after start")
    query = scope_deposits(select(Deposit), actor).where(Deposit.status.notin_(["RELEASED", "REJECTED", "RENEWED"]))
    events = [
        CalendarEvent(
            on_date=d.effective_maturity,
            type="MATURITY",
            deposit_id=d.id,
            reference_no=d.reference_no,
            status=d.status,
            renewal_due=d.status in {"EXPIRING", "MATURED"},
        )
        for d in db.scalars(query).all()
        if start <= d.effective_maturity <= end
    ]
    return sorted(events, key=lambda e: e.on_date)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    rows = db.execute(
        scope_deposits(select(Deposit.status, func.count()), actor).group_by(Deposit.status)
    ).all()
    counts = {status: 0 for status in STATUSES}
    counts.update({status: count for status, count in rows})

    today = today_ist()
    upcoming = []
    for d in db.scalars(scope_deposits(select(Deposit), actor).where(Deposit.status.in_(TRACKED | REMINDED))).all():
        days_left = (d.effective_maturity - today).days
        if days_left <= 90:
            upcoming.append(
                {
                    "deposit_id": d.id,
                    "reference_no": d.reference_no,
                    "maturity_date": d.effective_maturity.isoformat(),
                    "days_left": days_left,
                    "amount": float(d.amount),
                }
            )
    upcoming.sort(key=lambda item: item["days_left"])

    pending_query = (
        select(func.count())
        .select_from(ReleaseRequest)
        .join(Deposit, Deposit.id == ReleaseRequest.deposit_id)
        .where(ReleaseRequest.status == "PENDING")
    )
    if actor.role == "INSTITUTION_USER":
        pending_query = pending_query.where(Deposit.institution_id == actor.institution_id)
    pending_approvals = db.scalar(pending_query) or 0

    return {
        "counts": counts,
        "total": sum(counts.values()),
        "upcoming": upcoming[:10],
        "pending_approvals": pending_approvals,
    }


# ============================================================================
# FEATURE 1: Smart Deadline & Expiry Alerts Endpoint
# ============================================================================

@router.get("/deadlines", response_model=DeadlinesResponse)
def get_deadlines(
    filter_type: str = Query("all", alias="filter", pattern="^(all|expiring|overdue|pending_actions)$"),
    threshold: str = Query("all", pattern="^(all|30|15|7|overdue)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Retrieve dynamically calculated deadline alerts for FDR maturity, scrutiny, renewals, and approvals."""
    return deadline_service.get_deadlines(db, actor, filter_type=filter_type, threshold=threshold, limit=limit)


# ============================================================================
# FEATURE 3: Deficiency Report Generator Endpoints
# ============================================================================

@router.get("/deposits/{deposit_id}/deficiency-report/preview", response_model=DeficiencyReportPreview)
def get_deficiency_preview(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Compile and preview real deficiencies, discrepancies, and missing documents for an FDR record."""
    dep = get_deposit_or_404(db, deposit_id, actor)
    return deficiency_service.assess_deposit_deficiencies(db, dep, actor)


@router.post("/deposits/{deposit_id}/deficiency-report")
def generate_deficiency_report(
    deposit_id: int,
    body: Optional[DeficiencyReportGenerateIn] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    """Generate and stream an official, government-grade PDF deficiency report."""
    dep = get_deposit_or_404(db, deposit_id, actor)
    try:
        pdf_bytes = deficiency_service.generate_deficiency_pdf(db, dep, actor, body)
        clean_ref = dep.reference_no.replace("/", "_").replace("\\", "_")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="AICTE_Deficiency_Report_{clean_ref}.pdf"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/reports/deposits")
def export_deposits(
    group: str = Query("all"),
    fmt: str = Query("xlsx", alias="format", pattern="^(csv|xlsx|pdf)$"),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("REGULATOR_OFFICER", "APPROVING_AUTHORITY")),
):
    if group not in reports.GROUPS:
        raise HTTPException(status_code=400, detail=f"Unknown group {group}")
    statuses = reports.GROUPS[group]
    query = select(Deposit).order_by(Deposit.id)
    if statuses is not None:
        query = query.where(Deposit.status.in_(statuses))
    names = {i.id: i.name for i in db.scalars(select(Institution)).all()}
    rows = [reports.to_row(d, names) for d in db.scalars(query).all()]

    body = reports.build(fmt, f"FDR report: {group}", rows)
    return Response(
        content=body,
        media_type=reports.MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="fdr-{group}.{fmt}"'},
    )


@router.post("/admin/lifecycle-sweep")
def run_lifecycle_sweep(actor: Actor = Depends(require())):
    """Runs the daily maturity check now. The same check also runs every day on schedule."""
    return run_daily_check(trigger="manual")


@router.get("/admin/jobs")
def list_job_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require()),
):
    rows = db.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(limit)).all()
    return {
        "schedule": os.getenv("DAILY_CHECK_TIME", "08:00") + " Indian time",
        "runs": [
            {
                "id": r.id,
                "job": r.job,
                "trigger": r.trigger,
                "status": r.status,
                "detail": r.detail,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ],
    }
