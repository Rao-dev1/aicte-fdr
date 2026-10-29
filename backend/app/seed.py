"""Demo accounts and connected demonstration dataset for local testing.
Runs only when no users exist yet or when explicitly invoked.
"""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .demo_dataset import seed_demonstration_dataset
from .models import Institution, User
from .sms_service import normalize_phone

DEMO_USERS = [
    # username, full name, role, institution code (or None), password
    ("admin", "Portal Admin", "ADMIN", None, "Admin@12345"),
    ("officer1", "AICTE Regulation Officer", "REGULATOR_OFFICER", None, "Officer@12345"),
    ("approver1", "Approving Authority", "APPROVING_AUTHORITY", None, "Approver@12345"),
    ("institution1", "Deccan Institute Accounts", "INSTITUTION_USER", "DIT-PUNE", "Institute@12345"),
    ("institution2", "Western Valley Accounts", "INSTITUTION_USER", "WVCE-NASHIK", "Institute@12345"),
    ("institution3", "Sahyadri Institute Accounts", "INSTITUTION_USER", "SIAS-KOLHAPUR", "Institute@12345"),
    ("institution4", "Coastal Technical Accounts", "INSTITUTION_USER", "CTU-GOA", "Institute@12345"),
]


def seed_demo_users(db: Session, seed_dataset: bool = True) -> int:
    created = 0
    # Optional: your own mobile number, so demo accounts receive SMS alerts. Never hardcode real numbers here.
    demo_phone = normalize_phone(os.getenv("DEMO_PHONE"))
    for username, full_name, role, code, password in DEMO_USERS:
        uname = username.strip().lower()
        existing = db.scalar(select(User).where(User.username == uname))
        if existing is not None:
            continue

        institution_id = None
        if code:
            inst = db.scalar(select(Institution).where(Institution.code == code))
            if inst is None:
                inst = Institution(name=f"{code} Institution", code=code)
                db.add(inst)
                db.flush()
            institution_id = inst.id

        db.add(
            User(
                username=uname,
                full_name=full_name,
                email=f"{uname}@example.com",
                role=role,
                institution_id=institution_id,
                phone=demo_phone if role != "ADMIN" else None,
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        created += 1
    db.commit()

    # Seed demonstration dataset if enabled (disabled during unit tests via SEED_DEMO=0)
    if seed_dataset and os.getenv("SEED_DEMO", "1") == "1":
        seed_demonstration_dataset(db)
    return created


if __name__ == "__main__":
    from .db import SessionLocal

    with SessionLocal() as session:
        seed_demo_users(session)
        print("Demo users and dataset verified.")
