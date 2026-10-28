import os

# Tests always use local SQLite and a test upload folder. Set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test_fdr.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["SEED_DEMO"] = "0"  # the fixture seeds explicitly below
os.environ["SCHEDULER_ENABLED"] = "0"  # tests start the scheduler themselves when needed
os.environ["SENDGRID_API_KEY"] = ""  # tests must never send real email; emails are only logged
os.environ["AUTH_JWT_SECRET"] = "test-only-secret-that-is-long-enough-for-sha256-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed_demo_users  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_users(db)
    with TestClient(app) as c:
        yield c
