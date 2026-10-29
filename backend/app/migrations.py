"""Database migrations for new feature models:
- FDR Lineage Relations & Lifecycle Events (FDR TRACE)
- Release Readiness Evaluations
- Regulation Rules & Assessment Snapshots (Regulation-Version Replay)
- Integrity Findings & Integrity Actions (Cross-Record Integrity Network)
"""

from sqlalchemy import inspect, text
from .db import engine
from .models import Base


def ensure_user_phone_column() -> bool:
    """Adds users.phone to a database created before SMS support. Safe to call on every start-up."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return False
    if "phone" in {col["name"] for col in inspector.get_columns("users")}:
        return False
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(20)"))
    return True


def ensure_document_version_columns() -> list:
    """Adds version columns to documents in a database created before version history. Safe on every start-up."""
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return []
    existing = {col["name"] for col in inspector.get_columns("documents")}
    wanted = {"series_id": "INTEGER", "version": "INTEGER", "extracted_json": "TEXT"}
    added = [name for name in wanted if name not in existing]
    if not added:
        return []
    with engine.begin() as conn:
        for name in added:
            conn.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {wanted[name]}"))
        conn.execute(text("UPDATE documents SET version = 1 WHERE version IS NULL"))
        conn.execute(text("UPDATE documents SET series_id = id WHERE series_id IS NULL"))
    return added


def ensure_encrypted_deposit_fields() -> int:
    """Encrypts the FDR number and bank name of rows saved before encryption was added.
    Adds the lookup-hash columns and drops the old plain unique constraint. Safe on every start-up:
    rows that already have a lookup hash are skipped."""
    from .crypto import bank_hash, encrypt_text, fdr_number_hash

    inspector = inspect(engine)
    if "deposits" not in inspector.get_table_names():
        return 0
    cols = {c["name"] for c in inspector.get_columns("deposits")}
    postgres = engine.dialect.name == "postgresql"

    with engine.begin() as conn:
        if "reference_hash" not in cols:
            conn.execute(text("ALTER TABLE deposits ADD COLUMN reference_hash VARCHAR(64)"))
        if "bank_hash" not in cols:
            conn.execute(text("ALTER TABLE deposits ADD COLUMN bank_hash VARCHAR(64)"))
        if postgres:
            conn.execute(text("ALTER TABLE deposits DROP CONSTRAINT IF EXISTS deposits_reference_no_key"))
            for column in ("reference_no", "bank_name", "confirmed_reference_no", "confirmed_bank_name"):
                conn.execute(text(f"ALTER TABLE deposits ALTER COLUMN {column} TYPE TEXT"))

        pending = conn.execute(
            text("SELECT id, reference_no, bank_name, confirmed_reference_no, confirmed_bank_name FROM deposits WHERE reference_hash IS NULL")
        ).mappings().all()

        # Two FDRs that differ only by case or spaces would collide once lookups ignore case. Stop and say so.
        seen: dict[str, str] = {}
        for row in pending:
            key = row["reference_no"].strip().lower()
            if key in seen:
                raise RuntimeError(f"Cannot encrypt: FDR numbers {seen[key]!r} and {row['reference_no']!r} are duplicates ignoring case. Fix them first.")
            seen[key] = row["reference_no"]

        for row in pending:
            conn.execute(
                text(
                    "UPDATE deposits SET reference_no = :ref, reference_hash = :ref_hash, bank_name = :bank, bank_hash = :bank_hash, "
                    "confirmed_reference_no = :cref, confirmed_bank_name = :cbank WHERE id = :id"
                ),
                {
                    "id": row["id"],
                    "ref": encrypt_text(row["reference_no"]),
                    "ref_hash": fdr_number_hash(row["reference_no"]),
                    "bank": encrypt_text(row["bank_name"]),
                    "bank_hash": bank_hash(row["bank_name"]),
                    "cref": encrypt_text(row["confirmed_reference_no"]) if row["confirmed_reference_no"] else None,
                    "cbank": encrypt_text(row["confirmed_bank_name"]) if row["confirmed_bank_name"] else None,
                },
            )

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_deposits_reference_hash ON deposits (reference_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_deposits_bank_hash ON deposits (bank_hash)"))
    return len(pending)


def run_migrations():
    """Applies all table schema migrations safely without dropping any data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    Base.metadata.create_all(bind=engine)
    ensure_user_phone_column()
    ensure_document_version_columns()
    ensure_encrypted_deposit_fields()
    new_tables = set(inspect(engine).get_table_names())
    added = new_tables - existing_tables
    return {"status": "ok", "added_tables": list(added), "total_tables": len(new_tables)}


if __name__ == "__main__":
    result = run_migrations()
    print("Migration complete:", result)
