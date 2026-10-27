from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .lifecycle import STATUSES, lifecycle_sweep
from .models import AuditLog, Deposit, Institution, ReleaseRequest
from .schemas import (
    AuditOut,
    DepositCreate,
    DepositOut,
    DepositPage,
    InstitutionCreate,
    InstitutionOut,
    ReleaseDecision,
    ReleaseOut,
    VerifyIn,
)

router = APIRouter()

ROLES = {"INSTITUTION_USER", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "ADMIN"}
RENEWABLE = {"VERIFIED", "ACTIVE", "EXPIRING", "MATURED"}
RELEASABLE = {"ACTIVE", "EXPIRING", "MATURED"}
VERIFIABLE = {"SUBMITTED", "DISCREPANCY"}


# ---- Identity -------------------------------------------------------------
# Placeholder: trusts X-Role / X-User headers. Replace with verified Auth.js JWT claims before any real use.


@dataclass
class Actor:
    name: str
    role: str


def get_actor(x_role: str = Header(default=""), x_user: str = Header(default="")) -> Actor:
    if x_role not in ROLES:
        raise HTTPException(status_code=401, detail="Missing or unknown X-Role header")
    return Actor(name=x_user or "anonymous", role=x_role)


def require(*allowed: str):
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed:
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
    exists = db.scalar(select(Deposit.id).where(Deposit.reference_no == reference_no))
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"Reference {reference_no} already exists")


# ---- Institutions ---------------------------------------------------------


@router.post("/institutions", status_code=201, response_model=InstitutionOut)
def create_institution(
    body: InstitutionCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("ADMIN")),
):
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
    actor: Actor = Depends(require("INSTITUTION_USER", "ADMIN")),
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    query = select(Deposit)
    if status:
        query = query.where(Deposit.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Deposit.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DepositPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/deposits/{deposit_id}", response_model=DepositOut)
def get_deposit(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    return get_deposit_or_404(db, deposit_id)


@router.get("/deposits/{deposit_id}/history", response_model=list[AuditOut])
def deposit_history(deposit_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    get_deposit_or_404(db, deposit_id)
    return db.scalars(
        select(AuditLog)
        .where(AuditLog.entity == "deposit", AuditLog.entity_id == deposit_id)
        .order_by(AuditLog.id)
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

    mismatch = body.confirmed_amount is not None and Decimal(body.confirmed_amount) != dep.amount
    dep.status = "DISCREPANCY" if mismatch else "VERIFIED"
    audit(
        db,
        "deposit",
        dep.id,
        "VERIFIED" if not mismatch else "DISCREPANCY_FLAGGED",
        actor.name,
        f"submitted {dep.amount}, confirmed {body.confirmed_amount}. {body.observations}".strip(),
    )
    db.commit()
    db.refresh(dep)
    return dep


@router.post("/deposits/{deposit_id}/renew", status_code=201, response_model=DepositOut)
def renew_deposit(
    deposit_id: int,
    body: DepositCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER", "ADMIN")),
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


# ---- Release / refund -----------------------------------------------------


@router.post("/deposits/{deposit_id}/release", status_code=201, response_model=ReleaseOut)
def request_release(
    deposit_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("INSTITUTION_USER", "ADMIN")),
):
    dep = get_deposit_or_404(db, deposit_id)
    if dep.status not in RELEASABLE:
        raise HTTPException(status_code=409, detail=f"Cannot request release for status {dep.status}")
    pending = db.scalar(
        select(ReleaseRequest.id).where(
            ReleaseRequest.deposit_id == dep.id, ReleaseRequest.status == "PENDING"
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="A release request is already pending")

    rr = ReleaseRequest(
        deposit_id=dep.id,
        status="PENDING",
        status_before=dep.status,
        requested_by=actor.name,
        remarks="",
    )
    db.add(rr)
    dep.status = "RELEASE_REQUESTED"
    db.flush()
    audit(db, "deposit", dep.id, "RELEASE_REQUESTED", actor.name, f"request {rr.id}")
    db.commit()
    db.refresh(rr)
    return rr


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
        dep.status = rr.status_before  # restore the status the deposit had before the request
        action = "RELEASE_REJECTED"

    rr.decided_by = actor.name
    rr.remarks = body.remarks
    audit(db, "deposit", dep.id, action, actor.name, body.remarks)
    db.commit()
    db.refresh(rr)
    return rr


# ---- Dashboard and jobs ---------------------------------------------------


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    rows = db.execute(select(Deposit.status, func.count()).group_by(Deposit.status)).all()
    counts = {status: 0 for status in STATUSES}
    counts.update({status: count for status, count in rows})
    return {"counts": counts, "total": sum(counts.values())}


@router.post("/admin/lifecycle-sweep")
def run_lifecycle_sweep(
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require("ADMIN")),
):
    """Called daily by the scheduler (Inngest later). `as_of` lets an admin replay a date for testing."""
    changed = lifecycle_sweep(db, as_of or date.today())
    return {"changed": changed}
