"""Database migrations for new feature models:
- FDR Lineage Relations & Lifecycle Events (FDR TRACE)
- Release Readiness Evaluations
- Regulation Rules & Assessment Snapshots (Regulation-Version Replay)
- Integrity Findings & Integrity Actions (Cross-Record Integrity Network)
"""

from sqlalchemy import inspect
from .db import engine
from .models import Base


def run_migrations():
    """Applies all table schema migrations safely without dropping any data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    Base.metadata.create_all(bind=engine)
    new_tables = set(inspect(engine).get_table_names())
    added = new_tables - existing_tables
    return {"status": "ok", "added_tables": list(added), "total_tables": len(new_tables)}


if __name__ == "__main__":
    result = run_migrations()
    print("Migration complete:", result)
