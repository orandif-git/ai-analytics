"""Create a fresh e2e database owned by a NON-superuser role (so row-level security is enforced) and migrate it."""
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

admin = make_url(os.environ["AIA_E2E_ADMIN_URL"])
db = "aia_e2e"
eng = create_engine(admin, isolation_level="AUTOCOMMIT")
with eng.connect() as c:
    c.execute(text(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
    if not c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'aia_app'")).first():
        c.execute(text("CREATE ROLE aia_app LOGIN PASSWORD 'aia_app' NOSUPERUSER NOBYPASSRLS"))
    c.execute(text(f"CREATE DATABASE {db} OWNER aia_app"))
with create_engine(admin.set(database=db), isolation_level="AUTOCOMMIT").connect() as c:
    c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

app_url = admin.set(username="aia_app", password="aia_app", database=db).render_as_string(hide_password=False)
os.environ["AIA_DATABASE_URL"] = app_url
os.environ.setdefault("AIA_JWT_SECRET", "e2e-secret-e2e-secret-e2e-secret-0123456789")
os.environ.setdefault("AIA_SECRET_KEY", "x" * 43 + "=")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

api_dir = os.path.join(os.path.dirname(__file__), "..", "..", "api")
cfg = Config(os.path.join(api_dir, "alembic.ini"))
cfg.set_main_option("script_location", os.path.join(api_dir, "alembic"))
command.upgrade(cfg, "head")
print(app_url)

# A real JPEG for the camera-preview step (a plain scene is enough; the point is a decodable image).
import cv2  # noqa: E402
import numpy as np  # noqa: E402

img = np.full((360, 640, 3), (70, 80, 90), np.uint8)
cv2.rectangle(img, (0, 250), (640, 360), (110, 120, 130), -1)
cv2.rectangle(img, (250, 80), (390, 250), (50, 60, 160), -1)
cv2.putText(img, "TEST CAMERA", (200, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
cv2.imwrite(os.path.join(os.path.dirname(__file__), ".gen", "cam.jpg"), img)
