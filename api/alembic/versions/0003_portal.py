"""rules, webhooks, preview requests, camera status, zone event kinds"""
from alembic import op

revision = "0003"
down_revision = "0002"

TENANT_POLICY = """
    CREATE POLICY tenant_isolation ON {t}
    USING (app_is_superadmin() OR tenant_id = app_tenant_id())
    WITH CHECK (app_is_superadmin() OR tenant_id = app_tenant_id())
"""


def rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(TENANT_POLICY.format(t=table))


def upgrade() -> None:
    op.execute("ALTER TABLE events DROP CONSTRAINT events_kind_check")
    op.execute("""
        ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN
        ('detection', 'count', 'line_cross', 'heatmap', 'zone_enter', 'zone_exit', 'zone_dwell'))
    """)

    # Webhook settings move out of `tenants`: that table is writable by the superadmin only,
    # while tenant admins must manage their own webhook.
    op.execute("ALTER TABLE tenants DROP COLUMN webhook_url, DROP COLUMN webhook_secret")
    op.execute("""
        CREATE TABLE tenant_webhooks (
            tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            url text NOT NULL,
            secret_enc text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    rls("tenant_webhooks")

    op.execute("""
        ALTER TABLE cameras
            ADD COLUMN reference_snapshot_path text,
            ADD COLUMN reference_snapshot_at timestamptz,
            ADD COLUMN status text NOT NULL DEFAULT 'unknown',
            ADD COLUMN status_at timestamptz,
            ADD COLUMN fps real
    """)

    op.execute("""
        CREATE TABLE snapshot_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            camera_id uuid NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'claimed', 'done', 'error')),
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            claimed_at timestamptz,
            answered_at timestamptz
        )
    """)
    rls("snapshot_requests")

    op.execute("""
        CREATE TABLE rules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            camera_id uuid REFERENCES cameras(id) ON DELETE CASCADE,
            name text NOT NULL,
            event_kind text NOT NULL CHECK (event_kind IN ('detection', 'line_cross', 'zone_enter', 'zone_exit', 'zone_dwell')),
            label text CHECK (label IN ('person', 'vehicle')),
            params jsonb NOT NULL DEFAULT '{}',
            cooldown_s integer NOT NULL DEFAULT 60 CHECK (cooldown_s BETWEEN 0 AND 86400),
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    rls("rules")
    op.execute("""
        CREATE TABLE rule_fires (
            rule_id uuid NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
            camera_id uuid NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            last_fired_at timestamptz NOT NULL,
            PRIMARY KEY (rule_id, camera_id)
        )
    """)
    rls("rule_fires")

    op.execute("""
        CREATE TABLE webhook_deliveries (
            id bigserial PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            rule_id uuid REFERENCES rules(id) ON DELETE SET NULL,
            event_id bigint,
            payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            delivered_at timestamptz
        )
    """)
    op.execute("CREATE INDEX ON webhook_deliveries (status, next_attempt_at)")
    op.execute("CREATE INDEX ON webhook_deliveries (tenant_id, created_at DESC)")
    rls("webhook_deliveries")


def downgrade() -> None:
    for t in ["webhook_deliveries", "rule_fires", "rules", "snapshot_requests", "tenant_webhooks"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("ALTER TABLE cameras DROP COLUMN reference_snapshot_path, DROP COLUMN reference_snapshot_at, "
               "DROP COLUMN status, DROP COLUMN status_at, DROP COLUMN fps")
    op.execute("ALTER TABLE tenants ADD COLUMN webhook_url text, ADD COLUMN webhook_secret text")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_kind_check")
    op.execute("ALTER TABLE events ADD CONSTRAINT events_kind_check CHECK (kind IN ('detection', 'count', 'line_cross', 'heatmap'))")
