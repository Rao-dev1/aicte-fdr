import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .auth import _secret
from .auth_routes import router as auth_router
from .db import SessionLocal, engine
from .models import Base
from .scheduler import start_scheduler
from .seed import seed_demo_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    _secret()  # refuses to start without a strong AUTH_JWT_SECRET
    # Creates tables if missing. Replace with Alembic migrations before production.
    Base.metadata.create_all(bind=engine)
    # Demo accounts are off unless SEED_DEMO=1 is set (for local testing only).
    if os.getenv("SEED_DEMO", "0") == "1":
        with SessionLocal() as db:
            seed_demo_users(db)
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AICTE Security Deposit / FDR Portal API", version="0.4.0", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
