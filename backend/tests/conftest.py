import os

# Tests always use local SQLite and a test upload folder. Set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test_fdr.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
