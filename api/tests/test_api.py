import uuid

from tests.conftest import login
from app.vendors import build_rtsp_url


def make_tenant(client, superadmin, name=None, retention=None):
    name = name or f"Tenant {uuid.uuid4().hex[:6]}"
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    body = {"name": name, "owner_email": email, "owner_password": "owner-password-1"}
    if retention:
        body["retention_days"] = retention
    r = client.post("/admin/tenants", json=body, headers=superadmin)
    assert r.status_code == 201, r.text
    return r.json(), login(client, email, "owner-password-1")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_bad_login_and_no_token(client):
    assert client.post("/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code == 401
    assert client.get("/sites").status_code == 401


def test_default_retention_is_7_days_and_configurable(client, superadmin):
    t, _ = make_tenant(client, superadmin)
    assert t["retention_days"] == 7
    r = client.patch(f"/admin/tenants/{t['id']}", json={"retention_days": 30}, headers=superadmin)
    assert r.json()["retention_days"] == 30
    assert client.patch(f"/admin/tenants/{t['id']}", json={"retention_days": 0}, headers=superadmin).status_code == 422


def test_tenant_user_cannot_use_admin_api(client, superadmin):
    _, owner = make_tenant(client, superadmin)
    assert client.get("/admin/tenants", headers=owner).status_code == 403
    assert client.post("/admin/tenants", json={}, headers=owner).status_code in (403, 422)


def test_tenant_isolation(client, superadmin):
    _, a = make_tenant(client, superadmin)
    _, b = make_tenant(client, superadmin)
    site_a = client.post("/sites", json={"name": "A HQ"}, headers=a).json()
    site_b = client.post("/sites", json={"name": "B HQ"}, headers=b).json()
    cam = client.post(
        "/cameras",
        json={"site_id": site_a["id"], "name": "Door", "vendor": "dahua", "host": "1.2.3.4", "username": "admin", "password": "p@ss/word"},
        headers=a,
    )
    assert cam.status_code == 201, cam.text
    assert "password" not in cam.json() and "password_enc" not in cam.json()

    assert [s["name"] for s in client.get("/sites", headers=a).json()] == ["A HQ"]
    assert [s["name"] for s in client.get("/sites", headers=b).json()] == ["B HQ"]
    assert client.get("/cameras", headers=b).json() == []
    # B cannot attach a camera to A's site, nor delete A's camera or site
    r = client.post("/cameras", json={"site_id": site_a["id"], "name": "x", "host": "h"}, headers=b)
    assert r.status_code == 404
    assert client.delete(f"/cameras/{cam.json()['id']}", headers=b).status_code == 404
    assert client.delete(f"/sites/{site_a['id']}", headers=b).status_code == 404
    assert client.get("/sites", headers=a).json()[0]["id"] == site_a["id"]
    assert site_b["id"] != site_a["id"]


def test_camera_password_encrypted_at_rest(client, superadmin):
    from sqlalchemy import text

    from app.db import rls_session

    t, owner = make_tenant(client, superadmin)
    site = client.post("/sites", json={"name": "S"}, headers=owner).json()
    client.post("/cameras", json={"site_id": site["id"], "name": "C", "host": "h", "username": "u", "password": "secret-pw"}, headers=owner)
    with rls_session(superadmin=True) as s:
        stored = s.execute(text("SELECT password_enc FROM cameras WHERE tenant_id = :t"), {"t": t["id"]}).scalar_one()
    assert stored and "secret-pw" not in stored


def test_viewer_cannot_write_and_inactive_tenant_cannot_login(client, superadmin):
    from sqlalchemy import text

    from app.db import rls_session
    from app.security import hash_password

    t, owner = make_tenant(client, superadmin)
    with rls_session(superadmin=True) as s:
        s.execute(
            text("INSERT INTO users (tenant_id, email, password_hash, role) VALUES (:t, 'viewer@example.com', :h, 'viewer') ON CONFLICT DO NOTHING"),
            {"t": t["id"], "h": hash_password("viewer-password-1")},
        )
    viewer = login(client, "viewer@example.com", "viewer-password-1")
    assert client.post("/sites", json={"name": "x"}, headers=viewer).status_code == 403
    assert client.get("/sites", headers=viewer).status_code == 200

    client.patch(f"/admin/tenants/{t['id']}", json={"is_active": False}, headers=superadmin)
    r = client.post("/auth/login", json={"email": "viewer@example.com", "password": "viewer-password-1"})
    assert r.status_code == 401


def test_rls_blocks_cross_tenant_reads_even_with_raw_sql(client, superadmin):
    from sqlalchemy import text

    from app.db import rls_session

    ta, a = make_tenant(client, superadmin)
    tb, _ = make_tenant(client, superadmin)
    client.post("/sites", json={"name": "only-a"}, headers=a)
    with rls_session(tenant_id=tb["id"]) as s:
        assert s.execute(text("SELECT count(*) FROM sites")).scalar_one() == 0
        assert s.execute(text("SELECT count(*) FROM tenants")).scalar_one() == 1
    with rls_session() as s:  # no context at all
        assert s.execute(text("SELECT count(*) FROM sites")).scalar_one() == 0


def test_rtsp_url_templates():
    assert build_rtsp_url("dahua", "h", 554, 2, "sub", None, "admin", "p@ss") == "rtsp://admin:p%40ss@h:554/cam/realmonitor?channel=2&subtype=1"
    assert build_rtsp_url("dahua", "h", 554, 1, "main").endswith("channel=1&subtype=0")
    assert build_rtsp_url("hikvision", "h", 554, 1, "sub").endswith("/Streaming/Channels/102")
    assert build_rtsp_url("generic", "h", 8554, path="live/1").endswith("h:8554/live/1")
