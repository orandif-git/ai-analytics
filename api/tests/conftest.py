import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("AIA_TEST_ADMIN_URL", "postgresql+psycopg://postgres@localhost:5432/postgres")
APP_URL = make_url(ADMIN_URL).set(username="aia_app", password="aia_app", database="aia_test")

os.environ["AIA_DATABASE_URL"] = APP_URL.render_as_string(hide_password=False)
os.environ["AIA_JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["AIA_SECRET_KEY"] = Fernet.generate_key().decode()
os.environ["AIA_MEDIA_DIR"] = __import__("tempfile").mkdtemp(prefix="aia-media-")
os.environ["AIA_BOOTSTRAP_SUPERADMIN_EMAIL"] = "root@example.com"
os.environ["AIA_BOOTSTRAP_SUPERADMIN_PASSWORD"] = "root-password-123"


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh database owned by a NON-superuser role, so row-level security is really enforced."""
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS aia_test WITH (FORCE)"))
        if not c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'aia_app'")).first():
            c.execute(text("CREATE ROLE aia_app LOGIN PASSWORD 'aia_app' NOSUPERUSER NOBYPASSRLS"))
        c.execute(text("CREATE DATABASE aia_test OWNER aia_app"))
    with create_engine(make_url(ADMIN_URL).set(database="aia_test"), isolation_level="AUTOCOMMIT").connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def client(database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def superadmin(client):
    return login(client, "root@example.com", "root-password-123")
