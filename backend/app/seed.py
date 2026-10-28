"""Demo accounts for local testing. Runs only when no users exist yet. Change or delete these before any real use."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .models import Institution, User

DEMO_USERS = [
    # username, full name, role, institution code (or None), password
    ("admin", "Portal Admin", "ADMIN", None, "Admin@12345"),
    ("officer1", "AICTE Regulation Officer", "REGULATOR_OFFICER", None, "Officer@12345"),
    ("approver1", "Approving Authority", "APPROVING_AUTHORITY", None, "Approver@12345"),
    ("institution1", "VIT Pune Accounts", "INSTITUTION_USER", "VIT-PUNE", "Institute@12345"),
]


def seed_demo_users(db: Session) -> int:
    if db.scalar(select(User.id).limit(1)) is not None:
        return 0

    created = 0
    for username, full_name, role, code, password in DEMO_USERS:
        institution_id = None
        if code:
            inst = db.scalar(select(Institution).where(Institution.code == code))
            if inst is None:
                inst = Institution(name="Vishwakarma Institute of Technology, Pune", code=code)
                db.add(inst)
                db.flush()
            institution_id = inst.id
        db.add(
            User(
                username=username,
                full_name=full_name,
                email=f"{username}@example.com",
                role=role,
                institution_id=institution_id,
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        created += 1
    db.commit()
    return created
