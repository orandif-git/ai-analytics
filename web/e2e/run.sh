#!/usr/bin/env bash
# Runs the browser end-to-end tests against a real API + Postgres + built web app.
# Needs: AIA_E2E_ADMIN_URL (superuser URL of a Postgres server), python deps for ../api, node deps installed.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
API_PORT=8010; WEB_PORT=4173; HOOK_PORT=9100
pids=()
for port in $API_PORT $WEB_PORT $HOOK_PORT; do
  if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then echo "port $port is already in use (stale server from an earlier run?)"; exit 1; fi
done
cleanup() { for p in "${pids[@]:-}"; do pkill -P "$p" 2>/dev/null || true; kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

APP_URL=$("$PY" e2e/setup_db.py | tail -1)
export AIA_DATABASE_URL="$APP_URL" AIA_JWT_SECRET=e2e-secret-e2e-secret-e2e-secret-0123456789 AIA_SECRET_KEY="$("$PY" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
export AIA_BOOTSTRAP_SUPERADMIN_EMAIL=root@example.com AIA_BOOTSTRAP_SUPERADMIN_PASSWORD=root-password-123
export AIA_WEBHOOK_ALLOW_PRIVATE=1 AIA_WEBHOOK_INTERVAL_SECONDS=1 AIA_MEDIA_DIR="$(mktemp -d)"

(cd ../api && "$PY" -m uvicorn app.main:app --port $API_PORT --log-level warning) & pids+=($!)
"$PY" e2e/receiver.py $HOOK_PORT & pids+=($!)
VITE=./node_modules/.bin/vite   # run vite directly (not via npx) so $! is the server itself and cleanup really stops it
$VITE build >/dev/null
AIA_API="http://127.0.0.1:$API_PORT" $VITE preview --port $WEB_PORT --strictPort >/dev/null & pids+=($!)

for url in "http://127.0.0.1:$API_PORT/health" "http://127.0.0.1:$WEB_PORT/"; do
  for _ in $(seq 1 60); do curl -fs "$url" >/dev/null 2>&1 && break; sleep 0.5; done
  curl -fs "$url" >/dev/null || { echo "server did not start: $url"; exit 1; }
done
export AIA_E2E_WEB="http://127.0.0.1:$WEB_PORT" AIA_E2E_API="http://127.0.0.1:$API_PORT" AIA_E2E_HOOK="http://127.0.0.1:$HOOK_PORT"
npx playwright test "$@"
