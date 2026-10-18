import base64
import binascii
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.config import get_settings

MAX_SNAPSHOT_BYTES = 1_000_000


def save_snapshot(tenant_id: UUID, camera_id: UUID, ts: datetime, b64: str) -> str:
    """Store a JPEG under media_dir and return its path relative to media_dir."""
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("snapshot is not valid base64")
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot too large")
    if not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("snapshot is not a JPEG")
    rel = Path(str(tenant_id)) / str(camera_id) / ts.strftime("%Y%m%d") / f"{uuid4().hex}.jpg"
    full = Path(get_settings().media_dir) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    return rel.as_posix()


def media_path(rel: str) -> Path | None:
    """Resolve a stored relative path, refusing anything that escapes media_dir."""
    base = Path(get_settings().media_dir).resolve()
    full = (base / rel).resolve()
    if base not in full.parents:
        return None
    return full


def delete_snapshot(rel: str) -> None:
    full = media_path(rel)
    if full is not None:
        try:
            os.remove(full)
        except FileNotFoundError:
            pass
