import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import Principal, require_tenant_admin, tenant_db
from app.security import encrypt_secret
from app.vendors import build_rtsp_url

router = APIRouter(prefix="/cameras", tags=["cameras"])

Vendor = Literal["dahua", "hikvision", "axis", "uniview", "generic"]
# Never return password_enc.
PUBLIC_COLS = "id, site_id, name, vendor, host, port, channel, stream, path, username, enabled, analytics, created_at"


class CameraIn(BaseModel):
    site_id: UUID
    name: str = Field(min_length=1, max_length=200)
    vendor: Vendor = "generic"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=554, ge=1, le=65535)
    channel: int = Field(default=1, ge=1)
    stream: Literal["main", "sub"] = "sub"
    path: str | None = None
    username: str | None = None
    password: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_camera(body: CameraIn, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    # RLS hides other tenants' sites, so a foreign site_id is simply "not found".
    if s.execute(text("SELECT 1 FROM sites WHERE id = :i"), {"i": body.site_id}).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    row = s.execute(
        text(
            "INSERT INTO cameras (tenant_id, site_id, name, vendor, host, port, channel, stream, path, username, password_enc) "
            "VALUES (:t, :site, :name, :vendor, :host, :port, :channel, :stream, :path, :user, :pw) "
            f"RETURNING {PUBLIC_COLS}"
        ),
        {
            "t": p.tenant_id, "site": body.site_id, "name": body.name, "vendor": body.vendor,
            "host": body.host, "port": body.port, "channel": body.channel, "stream": body.stream,
            "path": body.path, "user": body.username,
            "pw": encrypt_secret(body.password) if body.password else None,
        },
    ).mappings().one()
    return {**row, "rtsp_url": build_rtsp_url(body.vendor, body.host, body.port, body.channel, body.stream, body.path, body.username, None)}


@router.get("")
def list_cameras(site_id: UUID | None = None, s: Session = Depends(tenant_db)):
    q = f"SELECT {PUBLIC_COLS} FROM cameras" + (" WHERE site_id = :site" if site_id else "") + " ORDER BY name"
    return [dict(r) for r in s.execute(text(q), {"site": site_id} if site_id else {}).mappings()]


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: UUID, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if s.execute(text("DELETE FROM cameras WHERE id = :i RETURNING id"), {"i": camera_id}).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


Point = Annotated[list[float], Field(min_length=2, max_length=2)]


class Line(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    p1: Point
    p2: Point
    # Which side counts as "in": the side the left-hand normal of p1->p2 points to when "left".
    in_side: Literal["left", "right"] = "left"


class Zone(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    polygon: list[Point] = Field(min_length=3, max_length=50)


class Analytics(BaseModel):
    """Coordinates are normalised 0-1 (x right, y down) so they survive resolution changes."""
    lines: list[Line] = Field(default=[], max_length=20)
    zones: list[Zone] = Field(default=[], max_length=20)


@router.put("/{camera_id}/analytics")
def set_analytics(camera_id: UUID, body: Analytics, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    for pt in [pt for l in body.lines for pt in (l.p1, l.p2)] + [pt for z in body.zones for pt in z.polygon]:
        if not all(0 <= v <= 1 for v in pt):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Coordinates must be between 0 and 1")
    row = s.execute(
        text(f"UPDATE cameras SET analytics = CAST(:a AS jsonb) WHERE id = :i RETURNING {PUBLIC_COLS}"),
        {"a": json.dumps(body.model_dump()), "i": camera_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    return dict(row)
