from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import tenant_db
from app.media import media_path

router = APIRouter(tags=["events"])

COLS = "id, camera_id, ts, kind, label, track_id, confidence, data, (snapshot_path IS NOT NULL) AS has_snapshot"


@router.get("/events")
def list_events(
    camera_id: UUID | None = None,
    kind: Literal["detection", "count", "line_cross", "heatmap"] | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    s: Session = Depends(tenant_db),
):
    q = f"SELECT {COLS} FROM events WHERE true"
    p: dict = {"lim": limit}
    if camera_id:
        q += " AND camera_id = :c"; p["c"] = camera_id
    if kind:
        q += " AND kind = :k"; p["k"] = kind
    if since:
        q += " AND ts >= :since"; p["since"] = since
    q += " ORDER BY ts DESC LIMIT :lim"
    return [dict(r) for r in s.execute(text(q), p).mappings()]


@router.get("/events/{event_id}/snapshot")
def event_snapshot(event_id: int, s: Session = Depends(tenant_db)):
    rel = s.execute(text("SELECT snapshot_path FROM events WHERE id = :i"), {"i": event_id}).scalar()
    path = media_path(rel) if rel else None
    if path is None or not path.is_file():
        raise HTTPException(404, "No snapshot")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/analytics/visitors")
def visitors(
    camera_id: UUID | None = None,
    since: datetime | None = None,
    bucket: Literal["hour", "day"] = "hour",
    s: Session = Depends(tenant_db),
):
    """Visitors counted by line crossings: direction 'in' per time bucket, plus 'out'."""
    since = since or datetime.now(timezone.utc) - timedelta(days=1)
    q = (
        f"SELECT date_trunc('{bucket}', ts) AS bucket, "  # bucket is a validated Literal
        "count(*) FILTER (WHERE data->>'direction' = 'in') AS entered, "
        "count(*) FILTER (WHERE data->>'direction' = 'out') AS exited "
        "FROM events WHERE kind = 'line_cross' AND label = 'person' AND ts >= :since"
        + (" AND camera_id = :c" if camera_id else "")
        + " GROUP BY 1 ORDER BY 1"
    )
    p = {"since": since, **({"c": camera_id} if camera_id else {})}
    return [dict(r) for r in s.execute(text(q), p).mappings()]


@router.get("/analytics/heatmap")
def heatmap(camera_id: UUID, since: datetime | None = None, s: Session = Depends(tenant_db)):
    """Sum per-minute sparse grid cells into one grid for the period."""
    since = since or datetime.now(timezone.utc) - timedelta(hours=1)
    rows = s.execute(
        text("SELECT data FROM events WHERE kind = 'heatmap' AND camera_id = :c AND ts >= :since"),
        {"c": camera_id, "since": since},
    ).scalars().all()
    grid = None
    cells: dict[str, int] = {}
    for d in rows:
        grid = grid or d.get("grid")
        for idx, n in d.get("cells", {}).items():
            cells[idx] = cells.get(idx, 0) + int(n)
    return {"grid": grid, "cells": cells}
