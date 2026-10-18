import hashlib
import json
import secrets
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import rls_session
from app.deps import Principal, require_superadmin
from app.media import save_snapshot
from app.security import decrypt_secret
from app.vendors import build_rtsp_url

router = APIRouter(tags=["edge"])
bearer = HTTPBearer(auto_error=False)

MAX_EVENTS_PER_REQUEST = 200


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- superadmin: manage devices ------------------------------------------------

class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.post("/admin/edge-devices", status_code=status.HTTP_201_CREATED)
def create_device(body: DeviceIn, _: Principal = Depends(require_superadmin)):
    token = "aia_" + secrets.token_urlsafe(32)
    with rls_session(superadmin=True) as s:
        row = s.execute(
            text("INSERT INTO edge_devices (name, token_hash) VALUES (:n, :h) RETURNING id, name, created_at"),
            {"n": body.name, "h": hash_token(token)},
        ).mappings().one()
    # The token is shown exactly once; only its hash is stored.
    return {**row, "token": token}


@router.get("/admin/edge-devices")
def list_devices(_: Principal = Depends(require_superadmin)):
    with rls_session(superadmin=True) as s:
        rows = s.execute(
            text("SELECT id, name, is_active, last_seen_at, agent_version, last_status, created_at FROM edge_devices ORDER BY created_at")
        ).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/admin/edge-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: UUID, _: Principal = Depends(require_superadmin)):
    with rls_session(superadmin=True) as s:
        if s.execute(text("UPDATE edge_devices SET is_active = false WHERE id = :i RETURNING id"), {"i": device_id}).first() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")


# ---- edge device API -------------------------------------------------------------

def edge_device(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UUID:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    # Token is looked up before any tenant is known, so this uses the system RLS context.
    with rls_session(superadmin=True) as s:
        row = s.execute(
            text("SELECT id FROM edge_devices WHERE token_hash = :h AND is_active"),
            {"h": hash_token(creds.credentials)},
        ).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device token")
    return row.id


@router.get("/edge/config")
def edge_config(device_id: UUID = Depends(edge_device)):
    """Enabled cameras of active tenants, with full RTSP URLs. Contains camera credentials."""
    with rls_session(superadmin=True) as s:
        rows = s.execute(
            text(
                "SELECT c.id, c.tenant_id, c.name, c.vendor, c.host, c.port, c.channel, c.stream, c.path, "
                "c.username, c.password_enc, c.analytics FROM cameras c JOIN tenants t ON t.id = c.tenant_id "
                "WHERE c.enabled AND t.is_active ORDER BY c.created_at"
            )
        ).mappings().all()
    cameras = []
    for r in rows:
        pw = decrypt_secret(r["password_enc"]) if r["password_enc"] else None
        cameras.append(
            {
                "id": r["id"], "tenant_id": r["tenant_id"], "name": r["name"],
                "rtsp_url": build_rtsp_url(r["vendor"], r["host"], r["port"], r["channel"], r["stream"], r["path"], r["username"], pw),
                "analytics": r["analytics"],
            }
        )
    return {"cameras": cameras}


class CameraStatus(BaseModel):
    camera_id: UUID
    status: Literal["online", "offline", "error"]
    fps: float | None = None


class Heartbeat(BaseModel):
    agent_version: str = Field(max_length=50)
    cameras: list[CameraStatus] = []


@router.post("/edge/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(body: Heartbeat, device_id: UUID = Depends(edge_device)):
    with rls_session(superadmin=True) as s:
        s.execute(
            text(
                "UPDATE edge_devices SET last_seen_at = now(), agent_version = :v, last_status = CAST(:st AS jsonb) WHERE id = :i"
            ),
            {"v": body.agent_version, "st": json.dumps([c.model_dump(mode="json") for c in body.cameras]), "i": device_id},
        )


class EventIn(BaseModel):
    client_id: UUID  # idempotency key: the agent retries from its outbox
    camera_id: UUID
    ts: datetime
    kind: Literal["detection", "count", "line_cross", "heatmap"]
    label: str | None = Field(default=None, max_length=50)
    track_id: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    data: dict = {}
    snapshot_b64: str | None = None


class EventsIn(BaseModel):
    events: list[EventIn] = Field(max_length=MAX_EVENTS_PER_REQUEST)


@router.post("/edge/events")
def ingest_events(body: EventsIn, device_id: UUID = Depends(edge_device)):
    accepted = rejected = 0
    with rls_session(superadmin=True) as s:
        tenants = {
            r.id: r.tenant_id
            for r in s.execute(
                text("SELECT id, tenant_id FROM cameras WHERE id = ANY(:ids)"),
                {"ids": list({e.camera_id for e in body.events})},
            )
        }
        for e in body.events:
            tenant_id = tenants.get(e.camera_id)
            if tenant_id is None:
                rejected += 1
                continue
            snap = None
            if e.snapshot_b64:
                try:
                    snap = save_snapshot(tenant_id, e.camera_id, e.ts, e.snapshot_b64)
                except ValueError:
                    rejected += 1
                    continue
            res = s.execute(
                text(
                    "INSERT INTO events (tenant_id, camera_id, client_id, ts, kind, label, track_id, confidence, data, snapshot_path) "
                    "VALUES (:t, :c, :cid, :ts, :k, :l, :tr, :cf, CAST(:d AS jsonb), :sp) "
                    "ON CONFLICT (tenant_id, client_id) DO NOTHING"
                ),
                {"t": tenant_id, "c": e.camera_id, "cid": e.client_id, "ts": e.ts, "k": e.kind, "l": e.label,
                 "tr": e.track_id, "cf": e.confidence, "d": json.dumps(e.data), "sp": snap},
            )
            if res.rowcount == 0 and snap:  # duplicate retry: don't leave an orphan file
                from app.media import delete_snapshot
                delete_snapshot(snap)
            accepted += 1  # duplicates count as accepted so the agent drops them from its outbox
    return {"accepted": accepted, "rejected": rejected}
