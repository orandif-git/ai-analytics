from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@contextmanager
def rls_session(tenant_id: UUID | None = None, superadmin: bool = False) -> Iterator[Session]:
    """Session whose Postgres row-level security context is set for the transaction.

    set_config(..., true) is transaction-local, so the context never leaks to another
    request that reuses the pooled connection.
    """
    with Session(get_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true), set_config('app.is_superadmin', :s, true)"),
            {"t": str(tenant_id) if tenant_id else "", "s": "on" if superadmin else "off"},
        )
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
