import base64
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import rls_session
from app.webhooks import WebhookUrlError, deliver_due, resolve_public, sign
from tests.conftest import login
from tests.test_api import make_tenant
from tests.test_edge import JPEG, device, ev, setup_camera


class Receiver:
    """Local HTTP server standing in for the customer's webhook endpoint."""

    def __init__(self):
        self.requests, self.status = [], 200
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append((dict(self.headers), body))
                self.send_response(outer.status)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def receiver():
    r = Receiver()
    yield r
    r.close()


def hook_and_rule(client, owner, receiver, **rule):
    secret = client.put("/settings/webhook", json={"url": receiver.url}, headers=owner).json()["secret"]
    body = {"name": "r", "event_kind": "line_cross", **rule}
    r = client.post("/rules", json=body, headers=owner)
    assert r.status_code == 201, r.text
    return secret, r.json()


def send(client, h, *events):
    r = client.post("/edge/events", json={"events": list(events)}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_webhook_is_signed_and_matches_rule_filters_with_cooldown(client, superadmin, receiver):
    t, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    secret, rule = hook_and_rule(client, owner, receiver, camera_id=cam["id"], label="person",
                                 params={"direction": "in", "line_id": "door"}, cooldown_s=3600)
    cross = lambda d, **kw: ev(cam, kind="line_cross", data={"line_id": "door", "direction": d}, **kw)
    send(client, h,
         cross("out"),                                      # wrong direction
         ev(cam, kind="line_cross", label="vehicle", data={"line_id": "door", "direction": "in"}),  # wrong label
         ev(cam, kind="line_cross", data={"line_id": "back", "direction": "in"}),                   # wrong line
         ev(cam, kind="detection"),                         # wrong kind
         cross("in"),                                       # matches
         cross("in"))                                       # matches but inside cooldown
    assert deliver_due() == 1
    (headers, body), = receiver.requests
    payload = json.loads(body)
    assert payload["type"] == "rule.triggered" and payload["rule"]["id"] == rule["id"]
    assert payload["camera"]["id"] == cam["id"] and payload["event"]["data"]["direction"] == "in"
    # Receiver can verify authenticity: HMAC-SHA256 over "<timestamp>.<raw body>"
    assert headers["X-AIA-Signature"] == sign(secret, headers["X-AIA-Timestamp"], body)
    assert sign("wrong-secret", headers["X-AIA-Timestamp"], body) != headers["X-AIA-Signature"]
    d = client.get("/webhook-deliveries", headers=owner).json()
    assert [x["status"] for x in d] == ["delivered"]


def test_failed_delivery_is_retried_then_succeeds(client, superadmin, receiver):
    _, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    hook_and_rule(client, owner, receiver, cooldown_s=0)
    receiver.status = 500
    send(client, h, ev(cam, kind="line_cross", data={"direction": "in"}))
    assert deliver_due() == 1
    d = client.get("/webhook-deliveries", headers=owner).json()[0]
    assert d["status"] == "pending" and d["attempts"] == 1 and d["last_error"] == "HTTP 500"
    assert deliver_due() == 0                                  # backed off, not due yet
    with rls_session(superadmin=True) as s:
        s.execute(text("UPDATE webhook_deliveries SET next_attempt_at = now() WHERE status = 'pending'"))
    receiver.status = 200
    assert deliver_due() == 1
    assert client.get("/webhook-deliveries", headers=owner).json()[0]["status"] == "delivered"


def test_test_button_and_no_webhook(client, superadmin, receiver):
    _, owner, _ = setup_camera(client, superadmin)
    assert client.post("/settings/webhook/test", headers=owner).status_code == 409
    client.put("/settings/webhook", json={"url": receiver.url}, headers=owner)
    assert client.post("/settings/webhook/test", headers=owner).status_code == 202
    deliver_due()
    assert json.loads(receiver.requests[-1][1])["type"] == "webhook.test"
    assert client.delete("/settings/webhook", headers=owner).status_code == 204
    assert client.get("/settings/webhook", headers=owner).json() == {"url": None}


def test_zone_events_trigger_zone_rules(client, superadmin, receiver):
    _, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    hook_and_rule(client, owner, receiver, event_kind="zone_dwell", params={"zone_id": "queue"}, cooldown_s=0)
    send(client, h, ev(cam, kind="zone_dwell", data={"zone_id": "other", "seconds": 40}),
         ev(cam, kind="zone_dwell", data={"zone_id": "queue", "seconds": 45}))
    assert deliver_due() == 1
    assert json.loads(receiver.requests[0][1])["event"]["data"]["zone_id"] == "queue"


@pytest.mark.parametrize("url", [
    "http://example.com/x",             # not https
    "https://127.0.0.1/x", "https://10.1.2.3/x", "https://192.168.0.5/x", "https://172.17.0.2/x",
    "https://169.254.169.254/latest/meta-data", "https://[::1]/x", "https://[::ffff:127.0.0.1]/x",
    "https://localhost/x", "https://0.0.0.0/x", "https://100.64.0.1/x",
    "https://user:pw@example.com/x",
])
def test_ssrf_guard_rejects_internal_targets(monkeypatch, url):
    monkeypatch.setattr(get_settings(), "webhook_allow_private", False)
    with pytest.raises(WebhookUrlError):
        resolve_public(url)


def test_ssrf_guard_applies_when_saving_a_webhook(client, superadmin, monkeypatch):
    _, owner, _ = setup_camera(client, superadmin)
    monkeypatch.setattr(get_settings(), "webhook_allow_private", False)
    r = client.put("/settings/webhook", json={"url": "https://169.254.169.254/x"}, headers=owner)
    assert r.status_code == 422 and "non-public" in r.json()["detail"]


def test_preview_request_roundtrip(client, superadmin):
    t, owner, cam = setup_camera(client, superadmin)
    _, other, _ = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    assert client.get(f"/cameras/{cam['id']}/preview.jpg", headers=owner).status_code == 404
    rid = client.post(f"/cameras/{cam['id']}/snapshot-request", headers=owner).json()["request_id"]
    assert client.get(f"/cameras/snapshot-requests/{rid}", headers=owner).json()["status"] == "pending"
    reqs = client.get("/edge/requests", headers=h).json()["requests"]
    mine = next(r for r in reqs if r["id"] == rid)
    assert mine["rtsp_url"].startswith("rtsp://admin:pw%2F1@10.0.0.5:554/")
    assert client.get("/edge/requests", headers=h).json()["requests"] == []      # claimed, not handed out twice
    assert client.post(f"/edge/requests/{rid}", json={"snapshot_b64": JPEG}, headers=h).status_code == 204
    assert client.get(f"/cameras/snapshot-requests/{rid}", headers=owner).json()["status"] == "done"
    img = client.get(f"/cameras/{cam['id']}/preview.jpg", headers=owner)
    assert img.status_code == 200 and img.content.startswith(b"\xff\xd8\xff")
    assert client.get(f"/cameras/{cam['id']}/preview.jpg", headers=other).status_code == 404   # tenant isolation
    assert client.get(f"/cameras/snapshot-requests/{rid}", headers=other).status_code == 404
    assert next(c for c in client.get("/cameras", headers=owner).json() if c["id"] == cam["id"])["has_preview"]
    assert client.post(f"/edge/requests/{rid}", json={"error": "late"}, headers=h).status_code == 404  # already answered


def test_preview_error_and_bad_image_are_reported(client, superadmin):
    _, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    for answer, expect in [({"error": "cannot open stream"}, "cannot open stream"),
                           ({"snapshot_b64": base64.b64encode(b"nope").decode()}, "not a JPEG")]:
        rid = client.post(f"/cameras/{cam['id']}/snapshot-request", headers=owner).json()["request_id"]
        client.get("/edge/requests", headers=h)
        client.post(f"/edge/requests/{rid}", json=answer, headers=h)
        st = client.get(f"/cameras/snapshot-requests/{rid}", headers=owner).json()
        assert st["status"] == "error" and expect in st["error"]


def test_stale_preview_request_expires(client, superadmin):
    _, owner, cam = setup_camera(client, superadmin)
    rid = client.post(f"/cameras/{cam['id']}/snapshot-request", headers=owner).json()["request_id"]
    with rls_session(superadmin=True) as s:
        s.execute(text("UPDATE snapshot_requests SET created_at = now() - interval '5 minutes' WHERE id = :i"), {"i": rid})
    st = client.get(f"/cameras/snapshot-requests/{rid}", headers=owner).json()
    assert st["status"] == "error" and "edge device" in st["error"]
    _, h = device(client, superadmin)
    assert all(r["id"] != rid for r in client.get("/edge/requests", headers=h).json()["requests"])


def test_heartbeat_sets_camera_status_visible_to_tenant(client, superadmin):
    _, owner, cam = setup_camera(client, superadmin)
    _, h = device(client, superadmin)
    assert client.get("/cameras", headers=owner).json()[0]["status"] == "unknown"
    client.post("/edge/heartbeat", json={"agent_version": "0.1", "cameras": [{"camera_id": cam["id"], "status": "online", "fps": 4.5}]}, headers=h)
    c = client.get("/cameras", headers=owner).json()[0]
    assert c["status"] == "online" and c["fps"] == 4.5 and c["status_at"]


def test_user_management_and_roles(client, superadmin):
    t, owner = make_tenant(client, superadmin)
    r = client.post("/users", json={"email": "view@example.com", "password": "viewer-pass-1", "role": "viewer"}, headers=owner)
    assert r.status_code == 201
    assert client.post("/users", json={"email": "view@example.com", "password": "viewer-pass-1", "role": "viewer"}, headers=owner).status_code == 409
    assert client.post("/users", json={"email": "x@example.com", "password": "viewer-pass-1", "role": "owner"}, headers=owner).status_code == 422
    viewer = login(client, "view@example.com", "viewer-pass-1")
    assert client.get("/users", headers=viewer).status_code == 403
    assert client.post("/rules", json={"name": "x", "event_kind": "detection"}, headers=viewer).status_code == 403
    assert client.get("/rules", headers=viewer).status_code == 200
    me = client.get("/auth/me", headers=viewer).json()
    assert me["email"] == "view@example.com" and me["tenant"]["retention_days"] == 7
    users = client.get("/users", headers=owner).json()
    owner_id = next(u["id"] for u in users if u["role"] == "owner")
    assert client.delete(f"/users/{owner_id}", headers=owner).status_code == 400          # not yourself
    assert client.delete(f"/users/{r.json()['id']}", headers=owner).status_code == 204
    assert client.post("/auth/login", json={"email": "view@example.com", "password": "viewer-pass-1"}).status_code == 401


def test_rules_webhooks_users_are_tenant_isolated(client, superadmin, receiver):
    _, a, cam_a = setup_camera(client, superadmin)
    _, b, cam_b = setup_camera(client, superadmin)
    hook_and_rule(client, a, receiver)
    assert client.get("/rules", headers=b).json() == []
    assert client.get("/settings/webhook", headers=b).json() == {"url": None}
    rid = client.get("/rules", headers=a).json()[0]["id"]
    assert client.patch(f"/rules/{rid}", json={"enabled": False}, headers=b).status_code == 404
    assert client.delete(f"/rules/{rid}", headers=b).status_code == 404
    # a rule cannot point at another tenant's camera
    r = client.post("/rules", json={"name": "x", "event_kind": "detection", "camera_id": cam_a["id"]}, headers=b)
    assert r.status_code == 404
    # tenant B's events never trigger A's rule
    _, h = device(client, superadmin)
    send(client, h, ev(cam_b, kind="line_cross", data={"direction": "in"}))
    assert deliver_due() == 0


def test_admin_tenant_list_has_counts(client, superadmin):
    t, owner, cam = setup_camera(client, superadmin)
    row = next(x for x in client.get("/admin/tenants", headers=superadmin).json() if x["id"] == t["id"])
    assert row["cameras"] == 1 and row["users"] == 1 and "webhook_url" not in row
