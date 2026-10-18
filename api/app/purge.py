"""Delete events and snapshots older than each tenant's retention_days."""
import asyncio
import logging

from sqlalchemy import text

from app.config import get_settings
from app.db import rls_session
from app.media import delete_snapshot

log = logging.getLogger("aia.purge")


def purge_expired() -> int:
    deleted = 0
    with rls_session(superadmin=True) as s:
        rows = s.execute(
            text(
                "DELETE FROM events e USING tenants t "
                "WHERE e.tenant_id = t.id AND e.ts < now() - make_interval(days => t.retention_days) "
                "RETURNING e.snapshot_path"
            )
        ).all()
    for (path,) in rows:
        deleted += 1
        if path:
            delete_snapshot(path)
    return deleted


async def purge_loop() -> None:
    interval = get_settings().purge_interval_seconds
    while True:
        try:
            n = await asyncio.to_thread(purge_expired)
            if n:
                log.info("purged %d expired events", n)
        except Exception:
            log.exception("purge failed")
        await asyncio.sleep(interval)
