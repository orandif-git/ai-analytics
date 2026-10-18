# ai-analytics

CCTV AI analytics for any RTSP/ONVIF camera. AI runs on a local Mac mini; the customer portal, API and PostgreSQL run on one Linux VPS. Multi-tenant.

| Folder | What |
|---|---|
| `api/` | FastAPI + PostgreSQL (row-level security per tenant). Phase 1 done. |
| `edge/` | Mac mini agent: RTSP, detection, counting, heatmap, outbox (phase 2). |
| `web/` | Customer portal and superadmin panel (phase 3). |
| `deploy/` | Docker Compose (Caddy, API, Postgres) for the VPS. |
| `docs/` | Architecture and decisions. |

## Run the API tests
Needs a Postgres reachable by a superuser (the tests create a separate non-superuser role so RLS is truly enforced):
```
pip install -e "api[dev]"
cd api
AIA_TEST_ADMIN_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest
```

## Deploy (VPS)
```
cd deploy && cp .env.example .env   # fill in secrets
docker compose up -d --build
```
The first start creates the `aia_app` role and database, runs migrations and creates the superadmin from `AIA_BOOTSTRAP_SUPERADMIN_*`.
