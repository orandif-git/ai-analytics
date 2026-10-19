from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from app.db import rls_session
from app.deps import Principal, get_principal
from app.security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(body: LoginIn):
    # Email is globally unique and the tenant is not yet known, so this lookup runs
    # with the system (superadmin) RLS context. Nothing else uses that context here.
    with rls_session(superadmin=True) as s:
        row = s.execute(
            text(
                "SELECT u.id, u.password_hash, u.role, u.tenant_id, u.is_active, "
                "coalesce(t.is_active, true) AS tenant_active "
                "FROM users u LEFT JOIN tenants t ON t.id = u.tenant_id WHERE u.email = :e"
            ),
            {"e": body.email.lower()},
        ).first()
    if (
        row is None
        or not verify_password(row.password_hash, body.password)
        or not row.is_active
        or not row.tenant_active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return {
        "access_token": create_token(row.id, row.role, row.tenant_id),
        "token_type": "bearer",
    }


@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    with rls_session(tenant_id=p.tenant_id, superadmin=p.is_superadmin) as s:
        u = s.execute(text("SELECT email FROM users WHERE id = :i"), {"i": p.user_id}).first()
        t = s.execute(text("SELECT name, retention_days FROM tenants WHERE id = :t"), {"t": p.tenant_id}).first() if p.tenant_id else None
    return {"user_id": p.user_id, "email": u.email if u else None, "role": p.role, "tenant_id": p.tenant_id,
            "tenant": {"name": t.name, "retention_days": t.retention_days} if t else None}
