"""tenants, users, sites, cameras, audit_log with row-level security"""
from alembic import op

revision = "0001"
down_revision = None

TENANT_TABLES = ["sites", "cameras", "audit_log"]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
        CREATE FUNCTION app_is_superadmin() RETURNS boolean LANGUAGE sql STABLE AS
        $$ SELECT coalesce(current_setting('app.is_superadmin', true), 'off') = 'on' $$
    """)
    op.execute("""
        CREATE FUNCTION app_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$
    """)

    op.execute("""
        CREATE TABLE tenants (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            retention_days integer NOT NULL DEFAULT 7 CHECK (retention_days BETWEEN 1 AND 365),
            webhook_url text,
            webhook_secret text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            email text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            role text NOT NULL CHECK (role IN ('superadmin', 'owner', 'admin', 'viewer')),
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((role = 'superadmin') = (tenant_id IS NULL))
        )
    """)
    op.execute("""
        CREATE TABLE sites (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE cameras (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            name text NOT NULL,
            vendor text NOT NULL DEFAULT 'generic',
            host text NOT NULL,
            port integer NOT NULL DEFAULT 554 CHECK (port BETWEEN 1 AND 65535),
            channel integer NOT NULL DEFAULT 1 CHECK (channel >= 1),
            stream text NOT NULL DEFAULT 'sub' CHECK (stream IN ('main', 'sub')),
            path text,
            username text,
            password_enc text,
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE audit_log (
            id bigserial PRIMARY KEY,
            tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            user_id uuid,
            action text NOT NULL,
            detail jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ON cameras (tenant_id, site_id)")
    op.execute("CREATE INDEX ON sites (tenant_id)")
    op.execute("CREATE INDEX ON audit_log (tenant_id, created_at DESC)")

    # Row-level security. FORCE makes it apply to the table owner too, so the app
    # role must not be a superuser (superusers always bypass RLS).
    for table in ["tenants", "users", *TENANT_TABLES]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON tenants
        USING (app_is_superadmin() OR id = app_tenant_id())
        WITH CHECK (app_is_superadmin())
    """)
    for table in ["users", *TENANT_TABLES]:
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (app_is_superadmin() OR tenant_id = app_tenant_id())
            WITH CHECK (app_is_superadmin() OR tenant_id = app_tenant_id())
        """)


def downgrade() -> None:
    for table in ["audit_log", "cameras", "sites", "users", "tenants"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS app_tenant_id()")
    op.execute("DROP FUNCTION IF EXISTS app_is_superadmin()")
