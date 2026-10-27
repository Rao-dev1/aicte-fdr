from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router
from .db import engine
from .models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates tables if missing. Replace with Alembic migrations before production.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AICTE Security Deposit / FDR Portal API", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
