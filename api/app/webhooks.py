"""Signed webhook delivery with retries.

Security: a tenant controls the webhook URL, so the server must not be tricked into calling its own
internal network (Postgres, cloud metadata, ...). Every delivery resolves the host, refuses anything that is
not a public address, and then connects to that exact IP (so DNS cannot change between check and use).
Redirects are not followed.
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.db import rls_session
from app.security import decrypt_secret

log = logging.getLogger("aia.webhooks")
MAX_ATTEMPTS = 8


class WebhookUrlError(ValueError):
    pass


def resolve_public(url: str) -> tuple[str, str, str, int]:
    """Validate the URL and return (scheme, ip, host, port). Raises WebhookUrlError."""
    allow_private = get_settings().webhook_allow_private
    parts = urlsplit(url)
    if parts.scheme != "https" and not (allow_private and parts.scheme == "http"):
        raise WebhookUrlError("webhook URL must use https")
    if not parts.hostname or parts.username or parts.password:
        raise WebhookUrlError("invalid webhook URL")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise WebhookUrlError("webhook host does not resolve")
    ips = []
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if addr.version == 6 and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        if not allow_private and (not addr.is_global or addr.is_multicast):
            raise WebhookUrlError("webhook host resolves to a non-public address")
        ips.append(str(addr))
    return parts.scheme, ips[0], parts.hostname, port


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def post_signed(url: str, secret: str, payload: dict, delivery_id: str) -> int:
    scheme, ip, host, port = resolve_public(url)
    body = json.dumps(payload, separators=(",", ":"), default=str).encode()
    ts = str(int(time.time()))
    parts = urlsplit(url)
    netloc = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
    target = parts._replace(netloc=netloc).geturl()
    headers = {
        "Host": parts.netloc,
        "Content-Type": "application/json",
        "X-AIA-Timestamp": ts,
        "X-AIA-Signature": sign(secret, ts, body),
        "X-AIA-Delivery": delivery_id,
        "User-Agent": "ai-analytics-webhook/1",
    }
    with httpx.Client(timeout=10, follow_redirects=False) as c:
        # sni_hostname makes TLS verify the certificate against the real host name, not the pinned IP.
        r = c.post(target, content=body, headers=headers, extensions={"sni_hostname": host})
    return r.status_code


def deliver_due(limit: int = 20) -> int:
    with rls_session(superadmin=True) as s:
        # Lease the rows for 60 s so a second worker (or a crash mid-send) cannot double-send immediately.
        rows = s.execute(
            text(
                "UPDATE webhook_deliveries SET next_attempt_at = now() + interval '60 seconds' WHERE id IN ("
                "SELECT id FROM webhook_deliveries WHERE status = 'pending' AND next_attempt_at <= now() "
                "ORDER BY id LIMIT :l FOR UPDATE SKIP LOCKED) RETURNING id, tenant_id, payload, attempts"
            ),
            {"l": limit},
        ).mappings().all()
    for r in rows:
        _attempt(r)
    return len(rows)


def _attempt(r) -> None:
    error: str | None = None
    with rls_session(superadmin=True) as s:
        hook = s.execute(text("SELECT url, secret_enc FROM tenant_webhooks WHERE tenant_id = :t"), {"t": r["tenant_id"]}).first()
    if hook is None:
        _finish(r, "failed", "no webhook configured")
        return
    try:
        code = post_signed(hook.url, decrypt_secret(hook.secret_enc), r["payload"], str(r["id"]))
        if 200 <= code < 300:
            _finish(r, "delivered", None)
            return
        error = f"HTTP {code}"
    except WebhookUrlError as ex:
        _finish(r, "failed", str(ex))  # retrying a forbidden URL is pointless
        return
    except Exception as ex:
        error = f"{type(ex).__name__}: {ex}"[:300]
    attempts = r["attempts"] + 1
    if attempts >= MAX_ATTEMPTS:
        _finish(r, "failed", error, attempts)
    else:
        delay = min(30 * 2 ** attempts, 3600)
        with rls_session(superadmin=True) as s:
            s.execute(
                text("UPDATE webhook_deliveries SET attempts = :a, last_error = :e, next_attempt_at = now() + make_interval(secs => :d) WHERE id = :i"),
                {"a": attempts, "e": error, "d": delay, "i": r["id"]},
            )


def _finish(r, status: str, error: str | None, attempts: int | None = None) -> None:
    with rls_session(superadmin=True) as s:
        s.execute(
            text(
                "UPDATE webhook_deliveries SET status = :st, last_error = :e, attempts = :a, "
                "delivered_at = CASE WHEN :st = 'delivered' THEN now() END WHERE id = :i"
            ),
            {"st": status, "e": error, "a": attempts if attempts is not None else r["attempts"] + 1, "i": r["id"]},
        )


async def webhook_loop() -> None:
    interval = get_settings().webhook_interval_seconds
    while True:
        try:
            await asyncio.to_thread(deliver_due)
        except Exception:
            log.exception("webhook delivery loop failed")
        await asyncio.sleep(interval)
