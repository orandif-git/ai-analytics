import type { EventRow } from "./types";

export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export const when = (iso: string) => new Date(iso).toLocaleString();

const KIND: Record<string, string> = {
  detection: "Detected", line_cross: "Crossed line", zone_enter: "Entered zone", zone_exit: "Left zone",
  zone_dwell: "Stayed in zone", count: "Count", heatmap: "Heatmap",
};
export const kindLabel = (k: string) => KIND[k] ?? k;

/** Names the user gave to lines/zones, by shape id. Falls back to the id. */
export type ShapeNames = Record<string, string>;

export function describe(e: EventRow, names: ShapeNames = {}): string {
  const who = e.label ?? "object";
  const d = e.data as Record<string, unknown>;
  const nm = (id: unknown) => names[String(id)] ?? String(id);
  switch (e.kind) {
    case "line_cross": return `${who} went ${d.direction} through "${nm(d.line_id)}"`;
    case "zone_enter": return `${who} entered "${nm(d.zone_id)}"`;
    case "zone_exit": return `${who} left "${nm(d.zone_id)}" after ${d.seconds}s`;
    case "zone_dwell": return `${who} has stayed in "${nm(d.zone_id)}" for ${d.seconds}s`;
    case "detection": return `${who} appeared${e.confidence ? ` (${Math.round(e.confidence * 100)}%)` : ""}`;
    case "count": return Object.entries((d.max ?? {}) as Record<string, number>).map(([k, v]) => `${v} ${k}`).join(", ") + " (max)";
    default: return e.kind;
  }
}
