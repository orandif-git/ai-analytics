#!/bin/sh
# Runs once on first start. Creates a NON-superuser role that owns the app database,
# because superusers bypass row-level security and would defeat tenant isolation.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres <<SQL
CREATE ROLE aia_app LOGIN PASSWORD '${AIA_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
CREATE DATABASE aia OWNER aia_app;
SQL
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d aia -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
