import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import Principal, require_superadmin, superadmin_db
from app.security import hash_password

router = APIRouter(prefix="/admin", tags=["superadmin"])

TENANT_COLS = "id, name, is_active, retention_days, created_at"


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=10)
    retention_days: int = Field(default=7, ge=1, le=365)


class TenantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    retention_days: int | None = Field(default=None, ge=1, le=365)


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    p: Principal = Depends(require_superadmin),
    s: Session = Depends(superadmin_db),
):
    tenant = s.execute(
        text(f"INSERT INTO tenants (name, retention_days) VALUES (:n, :r) RETURNING {TENANT_COLS}"),
        {"n": body.name, "r": body.retention_days},
    ).mappings().one()
    try:
        s.execute(
            text("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (:t, :e, :h, 'owner')"),
            {"t": tenant["id"], "e": body.owner_email.lower(), "h": hash_password(body.owner_password)},
        )
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Owner email already in use")
    s.execute(
        text("INSERT INTO audit_log (tenant_id, user_id, action) VALUES (:t, :u, 'tenant.create')"),
        {"t": tenant["id"], "u": p.user_id},
    )
    return dict(tenant)


@router.get("/tenants")
def list_tenants(s: Session = Depends(superadmin_db)):
    rows = s.execute(text(
        f"SELECT {TENANT_COLS}, "
        "(SELECT count(*) FROM cameras c WHERE c.tenant_id = tenants.id) AS cameras, "
        "(SELECT count(*) FROM users u WHERE u.tenant_id = tenants.id) AS users "
        "FROM tenants ORDER BY created_at"
    )).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/tenants/{tenant_id}")
def patch_tenant(
    tenant_id: UUID,
    body: TenantPatch,
    p: Principal = Depends(require_superadmin),
    s: Session = Depends(superadmin_db),
):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    # Column names come from the fixed pydantic model above, never from user input.
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    row = s.execute(
        text(f"UPDATE tenants SET {sets} WHERE id = :id RETURNING {TENANT_COLS}"),
        {**changes, "id": tenant_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    s.execute(
        text("INSERT INTO audit_log (tenant_id, user_id, action, detail) VALUES (:t, :u, 'tenant.update', CAST(:d AS jsonb))"),
        {"t": tenant_id, "u": p.user_id, "d": json.dumps(changes)},
    )
    return dict(row)
