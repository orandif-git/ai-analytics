import base64
import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import login
from tests.test_api import make_tenant

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


def setup_camera(client, superadmin, **kw):
    t, owner = make_tenant(client, superadmin, **kw)
    site = client.post("/sites", json={"name": "S"}, headers=owner).json()
    cam = client.post(
        "/cameras",
        json={"site_id": site["id"], "name": "Cam", "vendor": "dahua", "host": "10.0.0.5", "username": "admin", "password": "pw/1"},
        headers=owner,
    ).json()
    return t, owner, cam


def device(client, superadmin):
    r = client.post("/admin/edge-devices", json={"name": "mac-mini"}, headers=superadmin)
    assert r.status_code == 201
    return r.json(), {"Authorization": f"Bearer {r.json()['token']}"}


def ev(cam, **kw):
    return {"client_id": str(uuid.uuid4()), "camera_id": cam["id"], "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "detection", "label": "person", "track_id": 1, "confidence": 0.9, **kw}


def test_device_auth_and_config_includes_decrypted_rtsp(client, superadmin):
    t, owner, cam = setup_camera(client, superadmin)
    assert client.get("/edge/config").status_code == 401
    assert client.get("/edge/config", headers={"Authorization": "Bearer nope"}).status_code == 401
    # tenant users and tenant tokens cannot act as devices
    assert client.get("/edge/config", headers=owner).status_code == 401
    d, h = device(client, superadmin)
    cfg = client.get("/edge/config", headers=h).json()["cameras"]
    mine = next(c for c in cfg if c["id"] == cam["id"])
    assert mine["rtsp_url"] == "rtsp://admin:pw%2F1@10.0.0.5:554/cam/realmonitor?channel=1&subtype=1"
    # revoked token stops working
    assert client.delete(f"/admin/edge-devices/{d['id']}", headers=superadmin).status_code == 204
    assert client.get("/edge/config", headers=h).status_code == 401


def test_tenant_cannot_manage_devices(client, superadmin):
    _, owner, _ = setup_camera(client, superadmin)
    assert client.post("/admin/edge-devices", json={"name": "x"}, headers=owner).status_code == 403


def test_heartbeat_updates_device(client, superadmin):
    _, _, cam = setup_camera(client, superadmin)
    d, h = device(client, superadmin)
    r = client.post("/edge/heartbeat", json={"agent_version": "0.1", "cameras": [{"camera_id": cam["id"], "status": "online", "fps": 5}]}, headers=h)
    assert r.status_code == 204
    row = next(x for x in client.get("/admin/edge-devices", headers=superadmin).json() if x["id"] == d["id"])
    assert row["agent_version"] == "0.1" and row["last_seen_at"] and row["last_status"][0]["status"] == "online"


def test_events_ingest_is_idempotent_and_tenant_scoped(client, superadmin):
    ta, a, cam_a = setup_camera(client, superadmin)
    tb, b, cam_b = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    batch = [ev(cam_a, snapshot_b64=JPEG), ev(cam_b)]
    for _ in range(2):  # the agent retries the identical batch (same client_ids)
        r = client.post("/edge/events", json={"events": batch}, headers=h)
        assert r.json() == {"accepted": 2, "rejected": 0}
    assert len(client.get("/events", headers=a).json()) == 1
    assert len(client.get("/events", headers=b).json()) == 1
    got = client.get("/events", headers=a).json()[0]
    assert got["has_snapshot"]
    assert client.get(f"/events/{got['id']}/snapshot", headers=a).content.startswith(b"\xff\xd8\xff")
    assert client.get(f"/events/{got['id']}/snapshot", headers=b).status_code == 404  # other tenant


def test_bad_events_rejected(client, superadmin):
    _, _, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    bad_jpeg = base64.b64encode(b"not a jpeg").decode()
    r = client.post("/edge/events", json={"events": [ev(cam, snapshot_b64=bad_jpeg), ev({"id": str(uuid.uuid4())})]}, headers=h)
    assert r.json() == {"accepted": 0, "rejected": 2}


def test_purge_uses_each_tenants_retention(client, superadmin):
    from sqlalchemy import text

    from app.db import rls_session
    from app.purge import purge_expired

    t7, a7, cam7 = setup_camera(client, superadmin)  # default 7 days
    t30, a30, cam30 = setup_camera(client, superadmin, retention=30)
    _, h = device(client, superadmin)
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    client.post("/edge/events", json={"events": [ev(cam7, ts=old, snapshot_b64=JPEG), ev(cam30, ts=old, snapshot_b64=JPEG), ev(cam7)]}, headers=h)
    with rls_session(superadmin=True) as s:
        paths = s.execute(text("SELECT snapshot_path FROM events WHERE tenant_id = :t AND snapshot_path IS NOT NULL"), {"t": t7["id"]}).scalars().all()
    from app.media import media_path
    assert paths and media_path(paths[0]).exists()
    assert purge_expired() >= 1
    assert len(client.get("/events", headers=a7).json()) == 1       # the 10-day-old one is gone
    assert len(client.get("/events", headers=a30).json()) == 1      # 30-day tenant keeps it
    assert not media_path(paths[0]).exists()                         # file deleted too


def test_visitor_and_heatmap_analytics(client, superadmin):
    _, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    evs = [ev(cam, kind="line_cross", data={"line_id": "door", "direction": d}) for d in ["in", "in", "out"]]
    evs += [ev(cam, kind="heatmap", label=None, track_id=None, confidence=None, data={"grid": [4, 3], "cells": c}) for c in ({"1": 2, "5": 1}, {"1": 3})]
    assert client.post("/edge/events", json={"events": evs}, headers=h).json()["accepted"] == 5
    v = client.get("/analytics/visitors", params={"camera_id": cam["id"]}, headers=owner).json()
    assert sum(x["entered"] for x in v) == 2 and sum(x["exited"] for x in v) == 1
    hm = client.get("/analytics/heatmap", params={"camera_id": cam["id"]}, headers=owner).json()
    assert hm == {"grid": [4, 3], "cells": {"1": 5, "5": 1}}


def test_camera_analytics_validation(client, superadmin):
    _, owner, cam = setup_camera(client, superadmin)
    good = {"lines": [{"id": "door", "p1": [0.1, 0.5], "p2": [0.9, 0.5]}], "zones": [{"id": "queue", "polygon": [[0, 0], [1, 0], [1, 1]]}]}
    assert client.put(f"/cameras/{cam['id']}/analytics", json=good, headers=owner).status_code == 200
    bad = {"lines": [{"id": "x", "p1": [0, 0], "p2": [2, 0]}]}
    assert client.put(f"/cameras/{cam['id']}/analytics", json=bad, headers=owner).status_code == 422
    _, h = device(client, superadmin)
    mine = next(c for c in client.get("/edge/config", headers=h).json()["cameras"] if c["id"] == cam["id"])
    assert mine["analytics"]["lines"][0]["id"] == "door"
