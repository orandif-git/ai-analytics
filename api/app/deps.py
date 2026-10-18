from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import rls_session
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user_id: UUID
    role: str
    tenant_id: UUID | None

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"


def get_principal(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = decode_token(creds.credentials)
        return Principal(
            user_id=UUID(claims["sub"]),
            role=claims["role"],
            tenant_id=UUID(claims["tid"]) if claims.get("tid") else None,
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def require_superadmin(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Superadmin only")
    return p


def require_tenant_user(p: Principal = Depends(get_principal)) -> Principal:
    if p.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant user required")
    return p


def require_tenant_admin(p: Principal = Depends(require_tenant_user)) -> Principal:
    if p.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return p


def tenant_db(p: Principal = Depends(require_tenant_user)) -> Iterator[Session]:
    with rls_session(tenant_id=p.tenant_id) as session:
        yield session


def superadmin_db(p: Principal = Depends(require_superadmin)) -> Iterator[Session]:
    with rls_session(superadmin=True) as session:
        yield session
