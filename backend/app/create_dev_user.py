"""CLI utility to safely create or reset local development user accounts.
Usage:
  python -m app.create_dev_user --seed-demo
  python -m app.create_dev_user --username admin --role ADMIN --password MyPassword123 --name "Local Admin"
"""

import argparse
import sys
from pathlib import Path
from sqlalchemy import select

# Ensure backend root is on sys.path for direct script execution
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Institution, User
from app.seed import seed_demo_users


def create_or_update_user(
    username: str,
    password: str,
    role: str = "ADMIN",
    full_name: str = "Developer Admin",
    institution_code: str | None = None,
) -> User:
    username = username.strip().lower()
    role = role.strip().upper()
    valid_roles = {"ADMIN", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "INSTITUTION_USER"}
    if role not in valid_roles:
        raise ValueError(f"Invalid role: {role}. Allowed: {valid_roles}")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        institution_id = None
        if institution_code:
            inst = db.scalar(select(Institution).where(Institution.code == institution_code))
            if not inst:
                inst = Institution(name=f"Institution {institution_code}", code=institution_code)
                db.add(inst)
                db.flush()
            institution_id = inst.id

        if user:
            user.password_hash = hash_password(password)
            user.full_name = full_name
            user.role = role
            user.is_active = True
            if institution_id:
                user.institution_id = institution_id
            db.commit()
            print(f"[OK] Updated existing user '{username}' with new credentials.")
            return user
        else:
            new_user = User(
                username=username,
                full_name=full_name,
                email=f"{username}@example.com",
                role=role,
                institution_id=institution_id,
                password_hash=hash_password(password),
                is_active=True,
            )
            db.add(new_user)
            db.commit()
            print(f"[OK] Created new user '{username}' (role: {role}).")
            return new_user


def main():
    parser = argparse.ArgumentParser(description="Create or reset development accounts.")
    parser.add_argument("--seed-demo", action="store_true", help="Seed all standard demo accounts")
    parser.add_argument("--username", type=str, default="admin", help="Username")
    parser.add_argument("--password", type=str, default="Admin@12345", help="Password")
    parser.add_argument("--role", type=str, default="ADMIN", help="Role (ADMIN, REGULATOR_OFFICER, APPROVING_AUTHORITY, INSTITUTION_USER)")
    parser.add_argument("--name", type=str, default="Portal Admin", help="Full Name")
    parser.add_argument("--institution-code", type=str, default=None, help="Institution code (for INSTITUTION_USER)")

    args = parser.parse_args()

    if args.seed_demo:
        with SessionLocal() as db:
            count = seed_demo_users(db)
            print(f"[OK] Seeded {count} demo accounts into database.")
            return

    create_or_update_user(
        username=args.username,
        password=args.password,
        role=args.role,
        full_name=args.name,
        institution_code=args.institution_code,
    )


if __name__ == "__main__":
    main()
