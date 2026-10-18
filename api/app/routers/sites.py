from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import Principal, require_tenant_admin, tenant_db

router = APIRouter(prefix="/sites", tags=["sites"])


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_site(body: SiteIn, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    row = s.execute(
        text("INSERT INTO sites (tenant_id, name) VALUES (:t, :n) RETURNING id, name, created_at"),
        {"t": p.tenant_id, "n": body.name},
    ).mappings().one()
    return dict(row)


@router.get("")
def list_sites(s: Session = Depends(tenant_db)):
    return [dict(r) for r in s.execute(text("SELECT id, name, created_at FROM sites ORDER BY name")).mappings()]


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: UUID, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if s.execute(text("DELETE FROM sites WHERE id = :i RETURNING id"), {"i": site_id}).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
