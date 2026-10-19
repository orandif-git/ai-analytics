from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import Principal, require_tenant_admin, tenant_db
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    role: Literal["admin", "viewer"]


@router.get("")
def list_users(p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    return [dict(r) for r in s.execute(text("SELECT id, email, role, is_active, created_at FROM users ORDER BY created_at")).mappings()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: UserIn, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    try:
        row = s.execute(
            text("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (:t, :e, :h, :r) RETURNING id, email, role, is_active, created_at"),
            {"t": p.tenant_id, "e": body.email.lower(), "h": hash_password(body.password), "r": body.role},
        ).mappings().one()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")
    return dict(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if user_id == p.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete yourself")
    target = s.execute(text("SELECT role FROM users WHERE id = :i"), {"i": user_id}).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.role == "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The owner cannot be deleted")
    s.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
