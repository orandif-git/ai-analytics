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
