import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import reports, storage
from .db import get_db
from .lifecycle import REMINDED, STATUSES, TRACKED, lifecycle_sweep, mismatched_fields
from .models import AuditLog, Deposit, Document, Institution, Notification, ReleaseRequest, utcnow
from .schemas import (
    AuditOut,
    CalendarEvent,
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

ROLES = {"INSTITUTION_USER", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "ADMIN"}
RENEWABLE = {"VERIFIED", "ACTIVE", "EXPIRING", "MATURED"}
RELEASABLE = {"ACTIVE", "EXPIRING", "MATURED"}
VERIFIABLE = {"SUBMITTED", "DISCREPANCY"}

ALLOWED_UPLOADS = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# ---- Identity -------------------------------------------------------------
# Placeholder: trusts X-Role / X-User headers. Replace with verified login before real use.


@dataclass
class Actor:
    name: str
    role: str


def get_actor(x_role: str = Header(default=""), x_user: str = Header(default="")) -> Actor:
    if x_role not in ROLES:
        raise HTTPException(status_code=401, detail="Missing or unknown X-Role header")
    return Actor(name=x_user or "anonymous", role=x_role)


def require(*allowed: str):
    """ADMIN may do everything. Other roles must be listed."""

    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role != "ADMIN" and actor.role not in allowed:
            raise HTTPException(status_code=403, detail=f"Role {actor.role} may not perform this action")
        return actor

    return dependency


# ---- Helpers --------------------------------------------------------------


def audit(db: Session, entity: str, entity_id: int, action: str, actor: str, detail: str = "") -> None:
    db.add(AuditLog(entity=entity, entity_id=entity_id, action=action, actor=actor, detail=detail))


def get_deposit_or_404(db: Session, deposit_id: int) -> Deposit:
    dep = db.get(Deposit, deposit_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="Deposit not found")
    return dep


def ensure_reference_free(db: Session, reference_no: str) -> None:
    if db.scalar(select(Deposit.id).where(Deposit.reference_no == reference_no)) is not None:
        raise HTTPException(status_code=409, detail=f"Reference {reference_no} already exists")


def visible_to(actor: Actor, role: str) -> bool:
    return actor.role == "ADMIN" or actor.role == role


# ---- Institutions ---------------------------------------------------------


@router.post("/institutions", status_code=201, response_model=InstitutionOut)
def create_institution(body: InstitutionCreate, db: Session = Depends(get_db), actor: Actor = Depends(require())):
    if actor.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only ADMIN can create institutions")
    if db.scalar(select(Institution.id).where(Institution.code == body.code)) is not None:
        raise HTTPException(status_code=409, detail="Institution code already exists")
    inst = Institution(name=body.name, code=body.code)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    return db.scalars(select(Institution).order_by(Institution.id)).all()


# ---- Deposits -------------------------------------------------------------


@router.post("/deposits", status_code=201, response_model=DepositOut)
def create_deposit(
    body: DepositCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER")),
):
    if db.get(Institution, body.institution_id) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    ensure_reference_free(db, body.reference_no)
    dep = Deposit(**body.model_dump(), status="SUBMITTED")
    db.add(dep)
    db.flush()
    audit(db, "deposit", dep.id, "CREATED", actor.name, f"ref {dep.reference_no}, amount {dep.amount}")
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
    query = select(Deposit)
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
    return get_deposit_or_404(db, deposit_id)


@router.get("/deposits/{deposit_id}/history", response_model=list[AuditOut])
def deposit_history(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    get_deposit_or_404(db, deposit_id)
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
    dep = get_deposit_or_404(db, deposit_id)
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
    old = get_deposit_or_404(db, deposit_id)
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
    db.commit()
    db.refresh(new)
    return new


# ---- Documents ------------------------------------------------------------


@router.post("/deposits/{deposit_id}/documents", status_code=201, response_model=DocumentOut)
def upload_document(
    deposit_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER", "REGULATOR_OFFICER")),
):
    dep = get_deposit_or_404(db, deposit_id)
    ext = ALLOWED_UPLOADS.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status_code=415, detail="Only PDF, PNG and JPEG files are allowed")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")

    key = f"{uuid.uuid4().hex}{ext}"
    storage.save(key, data)
    doc = Document(
        deposit_id=dep.id,
        filename=Path(file.filename or "upload").name[:255],
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        storage_key=key,
        uploaded_by=actor.name,
        uploaded_at=utcnow(),
    )
    db.add(doc)
    db.flush()
    audit(db, "deposit", dep.id, "DOCUMENT_UPLOADED", actor.name, doc.filename)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/deposits/{deposit_id}/documents", response_model=list[DocumentOut])
def list_documents(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    get_deposit_or_404(db, deposit_id)
    return db.scalars(select(Document).where(Document.deposit_id == deposit_id).order_by(Document.id)).all()


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    path = storage.path_for(doc.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")
    return FileResponse(path, media_type=doc.content_type, filename=doc.filename)


# ---- Release / refund -----------------------------------------------------


@router.post("/deposits/{deposit_id}/release", status_code=201, response_model=ReleaseOut)
def request_release(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER")),
):
    dep = get_deposit_or_404(db, deposit_id)
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
    db.commit()
    db.refresh(rr)
    return rr


@router.get("/release-requests", response_model=list[ReleaseOut])
def list_release_requests(
    status: str = Query("PENDING"),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    return db.scalars(select(ReleaseRequest).where(ReleaseRequest.status == status).order_by(ReleaseRequest.id)).all()


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

    dep = get_deposit_or_404(db, rr.deposit_id)
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
    db.commit()
    db.refresh(rr)
    return rr


# ---- Notifications --------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    query = select(Notification).order_by(Notification.id.desc()).limit(100)
    if actor.role != "ADMIN":
        query = query.where(Notification.role == actor.role)
    return db.scalars(query).all()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    n = db.get(Notification, notification_id)
    if n is None or not visible_to(actor, n.role):
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


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
    deposits = db.scalars(select(Deposit).where(Deposit.status.notin_(["RELEASED", "REJECTED", "RENEWED"]))).all()
    events = [
        CalendarEvent(
            on_date=d.effective_maturity,
            type="MATURITY",
            deposit_id=d.id,
            reference_no=d.reference_no,
            status=d.status,
            renewal_due=d.status in {"EXPIRING", "MATURED"},
        )
        for d in deposits
        if start <= d.effective_maturity <= end
    ]
    return sorted(events, key=lambda e: e.on_date)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    rows = db.execute(select(Deposit.status, func.count()).group_by(Deposit.status)).all()
    counts = {status: 0 for status in STATUSES}
    counts.update({status: count for status, count in rows})

    today = date.today()
    upcoming = []
    for d in db.scalars(select(Deposit).where(Deposit.status.in_(TRACKED | REMINDED))).all():
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

    pending_approvals = db.scalar(
        select(func.count()).select_from(ReleaseRequest).where(ReleaseRequest.status == "PENDING")
    ) or 0
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "upcoming": upcoming[:10],
        "pending_approvals": pending_approvals,
    }


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
def run_lifecycle_sweep(
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require()),
):
    """Called daily by the scheduler (Inngest later). `as_of` lets an admin replay a date for testing."""
    if actor.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only ADMIN can run the sweep")
    return lifecycle_sweep(db, as_of or date.today())
