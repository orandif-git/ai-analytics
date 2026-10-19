import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import Principal, require_tenant_admin, tenant_db
from app.security import encrypt_secret
from app.webhooks import WebhookUrlError, resolve_public

router = APIRouter(tags=["settings"])


class WebhookIn(BaseModel):
    url: HttpUrl


@router.get("/settings/webhook")
def get_webhook(p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    row = s.execute(text("SELECT url, updated_at FROM tenant_webhooks")).mappings().first()
    return dict(row) if row else {"url": None}


@router.put("/settings/webhook")
def set_webhook(body: WebhookIn, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    """Set the URL and (re)generate the signing secret. The secret is returned ONCE."""
    url = str(body.url)
    try:
        resolve_public(url)  # refuse private/internal targets up front (checked again at every delivery)
    except WebhookUrlError as ex:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(ex))
    secret = "whsec_" + secrets.token_urlsafe(32)
    s.execute(
        text("INSERT INTO tenant_webhooks (tenant_id, url, secret_enc) VALUES (:t, :u, :s) "
             "ON CONFLICT (tenant_id) DO UPDATE SET url = :u, secret_enc = :s, updated_at = now()"),
        {"t": p.tenant_id, "u": url, "s": encrypt_secret(secret)},
    )
    return {"url": url, "secret": secret}


@router.delete("/settings/webhook", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    s.execute(text("DELETE FROM tenant_webhooks"))


@router.post("/settings/webhook/test", status_code=status.HTTP_202_ACCEPTED)
def test_webhook(p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if s.execute(text("SELECT 1 FROM tenant_webhooks")).first() is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No webhook configured")
    row = s.execute(
        text("INSERT INTO webhook_deliveries (tenant_id, payload) VALUES (:t, CAST(:p AS jsonb)) RETURNING id"),
        {"t": p.tenant_id, "p": json.dumps({"type": "webhook.test", "message": "Hello from AI Analytics"})},
    ).one()
    return {"delivery_id": row.id}


@router.get("/webhook-deliveries")
def list_deliveries(p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    rows = s.execute(
        text("SELECT id, rule_id, event_id, status, attempts, last_error, created_at, delivered_at, "
             "payload->>'type' AS type FROM webhook_deliveries ORDER BY id DESC LIMIT 50")
    ).mappings()
    return [dict(r) for r in rows]
