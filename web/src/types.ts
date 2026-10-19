export type Role = "superadmin" | "owner" | "admin" | "viewer";

export interface Me {
  user_id: string;
  email: string | null;
  role: Role;
  tenant_id: string | null;
  tenant: { name: string; retention_days: number } | null;
}

export type Point = [number, number];
export interface Line { id: string; name?: string | null; p1: Point; p2: Point; in_side: "left" | "right" }
export interface Zone { id: string; name?: string | null; polygon: Point[]; dwell_s: number }
export interface Analytics { lines: Line[]; zones: Zone[] }

export interface Site { id: string; name: string }
export interface Camera {
  id: string; site_id: string; name: string; vendor: string; host: string; port: number; channel: number;
  stream: "main" | "sub"; path: string | null; username: string | null; enabled: boolean;
  analytics: Partial<Analytics>; status: "online" | "offline" | "error" | "unknown"; status_at: string | null;
  fps: number | null; has_preview: boolean; reference_snapshot_at: string | null;
}

export type EventKind = "detection" | "count" | "line_cross" | "heatmap" | "zone_enter" | "zone_exit" | "zone_dwell";
export interface EventRow {
  id: number; camera_id: string; ts: string; kind: EventKind; label: string | null; track_id: number | null;
  confidence: number | null; data: Record<string, unknown>; has_snapshot: boolean;
}

export type RuleKind = "detection" | "line_cross" | "zone_enter" | "zone_exit" | "zone_dwell";
export interface Rule {
  id: string; camera_id: string | null; name: string; event_kind: RuleKind; label: "person" | "vehicle" | null;
  params: { direction?: "in" | "out"; line_id?: string; zone_id?: string }; cooldown_s: number; enabled: boolean;
}

export interface Delivery {
  id: number; type: string | null; status: "pending" | "delivered" | "failed"; attempts: number;
  last_error: string | null; created_at: string; delivered_at: string | null;
}
export interface UserRow { id: string; email: string; role: Role; is_active: boolean; created_at: string }
export interface TenantRow {
  id: string; name: string; is_active: boolean; retention_days: number; created_at: string; cameras: number; users: number;
}
export interface DeviceRow { id: string; name: string; is_active: boolean; last_seen_at: string | null; agent_version: string | null }
export interface VisitorBucket { bucket: string; entered: number; exited: number }
export interface Heatmap { grid: [number, number] | null; cells: Record<string, number> }
