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

## Phase 1 limits (known)
- JWTs are valid until expiry (60 min) even if a tenant is deactivated afterwards; only new logins are blocked.
- No refresh tokens, rate limiting or password reset yet (phase 5).
- Webhook delivery and signing are not implemented yet; `tenants.webhook_url/secret` columns exist.
