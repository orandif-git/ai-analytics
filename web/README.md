# Web portal

React + TypeScript + Vite. One app for customers and the platform admin; what you see depends on your role.

| Role | Pages |
|---|---|
| superadmin | Customers (create, retention, suspend), Edge devices (create/revoke tokens) |
| owner / admin | Dashboard, Cameras (add, draw lines and zones), Events, Rules & alerts, Settings (webhook, users) |
| viewer | Dashboard, Cameras, Events (read only) |

```
npm install
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000 (set AIA_API to change)
npm run typecheck && npm test
./e2e/run.sh         # browser tests against a real API + Postgres (see below)
```

## End-to-end tests
`e2e/run.sh` creates a fresh database (owned by a non-superuser role so row-level security applies), starts the API, a webhook receiver and the built portal, then drives a headless Chromium through the whole flow: create customer, add camera, camera preview, draw line and zone, webhook + rule, signed delivery, dashboard, events, viewer permissions, phone layout.
```
AIA_E2E_ADMIN_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres PYTHON=python ./e2e/run.sh
```
The edge agent is played by test code that calls the same HTTP API (the real one needs a camera).

## Notes
- Pictures need the login token, which `<img>` cannot send, so they are fetched and shown from blob URLs.
- The login token lives in `sessionStorage` (cleared when the tab closes) and lasts 60 minutes. There is no refresh token yet.
