"""edge devices (platform level), events, camera analytics config"""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    # Edge devices (the Mac mini) are platform-level: one device serves many tenants,
    # so only the superadmin can see them. The tenant comes from each camera.
    op.execute("""
        CREATE TABLE edge_devices (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            token_hash text NOT NULL UNIQUE,
            is_active boolean NOT NULL DEFAULT true,
            last_seen_at timestamptz,
            agent_version text,
            last_status jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE edge_devices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE edge_devices FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY superadmin_only ON edge_devices USING (app_is_superadmin()) WITH CHECK (app_is_superadmin())")

    # Normalised (0-1) lines and zones drawn in the portal (phase 3) and read by the edge agent.
    op.execute("ALTER TABLE cameras ADD COLUMN analytics jsonb NOT NULL DEFAULT '{}'")

    op.execute("""
        CREATE TABLE events (
            id bigserial PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            camera_id uuid NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            client_id uuid NOT NULL,
            ts timestamptz NOT NULL,
            kind text NOT NULL CHECK (kind IN ('detection', 'count', 'line_cross', 'heatmap')),
            label text,
            track_id integer,
            confidence real,
            data jsonb NOT NULL DEFAULT '{}',
            snapshot_path text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, client_id)
        )
    """)
    op.execute("CREATE INDEX ON events (tenant_id, camera_id, ts DESC)")
    op.execute("CREATE INDEX ON events (tenant_id, kind, ts DESC)")
    op.execute("ALTER TABLE events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON events
        USING (app_is_superadmin() OR tenant_id = app_tenant_id())
        WITH CHECK (app_is_superadmin() OR tenant_id = app_tenant_id())
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS events CASCADE")
    op.execute("ALTER TABLE cameras DROP COLUMN IF EXISTS analytics")
    op.execute("DROP TABLE IF EXISTS edge_devices CASCADE")
