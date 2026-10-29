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


def run_migrations():
    """Applies all table schema migrations safely without dropping any data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    Base.metadata.create_all(bind=engine)
    ensure_user_phone_column()
    new_tables = set(inspect(engine).get_table_names())
    added = new_tables - existing_tables
    return {"status": "ok", "added_tables": list(added), "total_tables": len(new_tables)}


if __name__ == "__main__":
    result = run_migrations()
    print("Migration complete:", result)
