# Architecture

## Topology
- **VPS (Linux)**: Caddy (TLS) -> FastAPI -> PostgreSQL, all in Docker Compose. Postgres is not published to the internet.
- **Mac mini (office)**: edge agent pulling RTSP **substreams** from camera sites. It only makes outbound calls to the VPS API.
- **Customer sites**: cameras reached by RTSP through a port forward on the customer's router.

## Decision: camera connectivity (chosen by owner)
Port-forward RTSP (TCP 554 or a chosen port) on the customer router, **restricted to the office's static public IP**.
Requirements for each site: public IP or DDNS (not CGNAT), router rule allowing only the office IP, strong unique camera password, UPnP and P2P disabled. Documented fallbacks if a site cannot do this: router VPN (WireGuard), or a small gateway device.
Bandwidth: analytics uses the sub stream (about 0.5-1 Mbps per camera) into the office.

## Multi-tenancy
Every tenant-owned table has `tenant_id` and PostgreSQL row-level security (`FORCE`). Each request sets `app.tenant_id` / `app.is_superadmin` with transaction-local `set_config`. The app connects as a non-superuser role (superusers bypass RLS). Superadmin users have `tenant_id NULL`.

## Retention
`tenants.retention_days` (default 7, 1-365), edited by the superadmin via `PATCH /admin/tenants/{id}`. The purge job that enforces it arrives with media storage in phase 2.

## Secrets
Camera passwords are Fernet-encrypted at rest (`AIA_SECRET_KEY`) and never returned by the API. User passwords use argon2.

## Edge devices and events (phase 2)
- Edge devices are **platform level** (superadmin creates them; the token is shown once and only its SHA-256 is stored). The one Mac mini serves every tenant, and `POST /edge/events` derives each event's tenant from its camera.
- `GET /edge/config` returns enabled cameras of active tenants with full RTSP URLs including decrypted credentials, so a device token is as sensitive as a camera password. Revoke with `DELETE /admin/edge-devices/{id}`.
- Events carry a `client_id`; the API ignores duplicates, so the agent can safely retry its outbox.
- Snapshots are JPEGs on the VPS under `AIA_MEDIA_DIR` (Docker volume `media`). An hourly job deletes events and snapshots older than each tenant's `retention_days`.
- Camera `analytics` (JSONB) holds normalised lines and zones; `PUT /cameras/{id}/analytics` sets them (the canvas editor arrives in phase 3).
- Visitor count = `line_cross` events with `direction=in`; `GET /analytics/visitors` buckets them by hour or day. `GET /analytics/heatmap` sums the per-minute grids.

## Portal, rules and webhooks (phase 3)
- **Portal** (`web/`): React app served by Caddy from the same origin as the API (`/api/*` is proxied, prefix stripped). Roles: superadmin (customers, retention, edge devices), owner/admin (everything for their company), viewer (read only).
- **Camera preview**: the VPS cannot reach cameras (port-forward is locked to the office IP), so the portal creates a `snapshot_request`; the edge agent polls `/edge/requests` every 3 s, grabs one frame and uploads it. The picture is what customers draw on.
- **Drawing**: lines and zones are saved as normalised 0-1 coordinates in `cameras.analytics`; the edge agent re-reads them every 60 s. A line's `in_side` is the side of p1 -> p2 (as seen on screen) that counts as "in"; the portal draws an IN marker on that side, and both sides are unit-tested to agree.
- **Zone events** (edge): `zone_enter`, `zone_exit` and `zone_dwell` (once per visit after the zone's `dwell_s`).
- **Rules**: match an event kind (+ optional label, line/zone id, direction) on one camera or all, with a per-(rule, camera) cooldown claimed atomically in SQL. A match queues a webhook delivery.
- **Webhooks**: one URL per tenant, signed `X-AIA-Signature: sha256=HMAC(secret, timestamp + "." + body)`, retried with backoff (30 s doubling, max 1 h, 8 attempts). The signing secret is shown once and stored encrypted.
- **SSRF guard**: a tenant chooses the URL, so every delivery requires https, resolves the host, refuses anything that is not a public address (loopback, private, link-local, CGNAT, IPv4-mapped IPv6, ...), connects to the resolved IP (TLS still verifies the real host name) and does not follow redirects.
- **Startup checks**: the API refuses to start with a JWT secret under 32 characters or an invalid encryption key.
- Browser tests: `web/e2e` drives the whole flow against a real API and Postgres.

## Phase 3 limits (known)
- Login tokens last 60 minutes with no refresh token, and a suspended tenant's existing tokens stay valid until they expire. No login rate limiting, password reset or 2FA yet (phase 5).
- Rules react to events; there is no "more than N people in a zone" rule yet.
- The superadmin cannot reset a customer's owner password from the UI yet.
- Webhook deliveries are processed by a loop inside the API process; fine for one VPS, move to a separate worker if the API is ever scaled out (the row lease already prevents double sends).
- Retention counts events and snapshots only. The camera preview picture is kept until replaced.

## Phase 2 limits (known)
- The YOLO detector and ByteTrack are NOT covered by automated tests and were not run in development (no torch in the dev sandbox, and the Mac mini was not available). Run `aia-edge probe` and a short supervised `aia-edge run` on the Mac mini before trusting counts, and benchmark cameras per Mac mini there.
- One YOLO model instance per camera (tracker state is per instance), which costs memory; a shared batched model is a later optimisation.
- Number-plate reading (India) is phase 4 and will run only on vehicle crops.
- Zones (dwell, restricted areas) are stored but not evaluated yet; only lines, counts and the heatmap are.
- The agent has no auto-update or launchd service file yet.

## Phase 1 limits (known)
- JWTs are valid until expiry (60 min) even if a tenant is deactivated afterwards; only new logins are blocked.
- No refresh tokens, rate limiting or password reset yet (phase 5).
- Webhook delivery and signing are not implemented yet; `tenants.webhook_url/secret` columns exist.
