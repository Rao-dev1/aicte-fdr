import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .advanced_routes import router as advanced_router
from .api import router
from .auth import _secret
from .auth_routes import router as auth_router
from .db import SessionLocal, engine
from .models import Base
from .scheduler import start_scheduler
from .seed import seed_demo_users
from .services.regulation_service import ensure_default_regulations_seeded


@asynccontextmanager
async def lifespan(app: FastAPI):
    _secret()  # refuses to start without a strong AUTH_JWT_SECRET
    # Creates tables if missing.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_default_regulations_seeded(db)
        # Seed demo users if SEED_DEMO=1 (default for local development)
        if os.getenv("SEED_DEMO", "1") == "1":
            seed_demo_users(db)
        db.commit()
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AICTE Security Deposit / FDR Portal API", version="0.5.0", lifespan=lifespan)

origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def handle_private_network_access(request, call_next):
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network"):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")
app.include_router(advanced_router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok"}
