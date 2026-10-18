from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config import get_settings
from app.db import rls_session
from app.routers import admin, auth, cameras, sites
from app.security import hash_password


def bootstrap_superadmin() -> None:
    s = get_settings()
    if not (s.bootstrap_superadmin_email and s.bootstrap_superadmin_password):
        return
    with rls_session(superadmin=True) as db:
        db.execute(
            text(
                "INSERT INTO users (email, password_hash, role) VALUES (:e, :h, 'superadmin') "
                "ON CONFLICT (email) DO NOTHING"
            ),
            {"e": s.bootstrap_superadmin_email.lower(), "h": hash_password(s.bootstrap_superadmin_password)},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_superadmin()
    yield


app = FastAPI(title="AI Analytics API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(sites.router)
app.include_router(cameras.router)


@app.get("/health")
def health():
    return {"status": "ok"}
