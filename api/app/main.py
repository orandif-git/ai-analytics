import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config import get_settings
from app.db import rls_session
from app.purge import purge_loop
from app.webhooks import webhook_loop
from app.routers import admin, auth, cameras, edge, events, rules, settings, sites, users
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
    tasks = [asyncio.create_task(purge_loop()), asyncio.create_task(webhook_loop())]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()


app = FastAPI(title="AI Analytics API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(sites.router)
app.include_router(cameras.router)
app.include_router(edge.router)
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(settings.router)
app.include_router(users.router)


@app.get("/health")
def health():
    return {"status": "ok"}
