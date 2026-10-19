import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import Principal, require_tenant_admin, tenant_db

router = APIRouter(prefix="/rules", tags=["rules"])

COLS = "id, camera_id, name, event_kind, label, params, cooldown_s, enabled, created_at"


class RuleParams(BaseModel):
    direction: Literal["in", "out"] | None = None   # line_cross
    line_id: str | None = Field(default=None, max_length=50)
    zone_id: str | None = Field(default=None, max_length=50)


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    camera_id: UUID | None = None   # None = every camera of the tenant
    event_kind: Literal["detection", "line_cross", "zone_enter", "zone_exit", "zone_dwell"]
    label: Literal["person", "vehicle"] | None = None
    params: RuleParams = RuleParams()
    cooldown_s: int = Field(default=60, ge=0, le=86400)
    enabled: bool = True


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if body.camera_id and s.execute(text("SELECT 1 FROM cameras WHERE id = :i"), {"i": body.camera_id}).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    row = s.execute(
        text(f"INSERT INTO rules (tenant_id, camera_id, name, event_kind, label, params, cooldown_s, enabled) "
             f"VALUES (:t, :c, :n, :k, :l, CAST(:p AS jsonb), :cd, :en) RETURNING {COLS}"),
        {"t": p.tenant_id, "c": body.camera_id, "n": body.name, "k": body.event_kind, "l": body.label,
         "p": json.dumps(body.params.model_dump(exclude_none=True)), "cd": body.cooldown_s, "en": body.enabled},
    ).mappings().one()
    return dict(row)


@router.get("")
def list_rules(s: Session = Depends(tenant_db)):
    return [dict(r) for r in s.execute(text(f"SELECT {COLS} FROM rules ORDER BY created_at")).mappings()]


class RulePatch(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cooldown_s: int | None = Field(default=None, ge=0, le=86400)


@router.patch("/{rule_id}")
def patch_rule(rule_id: UUID, body: RulePatch, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys come from the fixed model above
    row = s.execute(text(f"UPDATE rules SET {sets} WHERE id = :id RETURNING {COLS}"), {**changes, "id": rule_id}).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return dict(row)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: UUID, p: Principal = Depends(require_tenant_admin), s: Session = Depends(tenant_db)):
    if s.execute(text("DELETE FROM rules WHERE id = :i RETURNING id"), {"i": rule_id}).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
