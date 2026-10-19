import type { Line, Point, Zone } from "./types";

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const round = (v: number) => Math.round(v * 10000) / 10000;

/** Pointer position on the picture -> normalised 0-1 coordinates (what the edge agent expects). */
export function toNormalized(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): Point {
  if (rect.width <= 0 || rect.height <= 0) return [0, 0];
  return [round(clamp01((clientX - rect.left) / rect.width)), round(clamp01((clientY - rect.top) / rect.height))];
}

/** Unit vector pointing to the side people stand on AFTER entering. Matches the edge agent's `in_side` rule:
 * the "left" of p1 -> p2 as seen on screen (y axis points down), i.e. the vector (dy, -dx). */
export function inDirection(line: Pick<Line, "p1" | "p2" | "in_side">): Point {
  const dx = line.p2[0] - line.p1[0];
  const dy = line.p2[1] - line.p1[1];
  const len = Math.hypot(dx, dy) || 1;
  const [nx, ny] = [dy / len, -dx / len];
  return line.in_side === "left" ? [nx, ny] : [-nx, -ny];
}

export const midpoint = (a: Point, b: Point): Point => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

export function nextId(prefix: string, existing: { id: string }[]): string {
  const used = new Set(existing.map((e) => e.id));
  for (let i = 1; ; i++) if (!used.has(`${prefix}${i}`)) return `${prefix}${i}`;
}

/** A line needs two distinct points; a zone needs a real area. */
export function lineIsValid(l: Pick<Line, "p1" | "p2">): boolean {
  return Math.hypot(l.p2[0] - l.p1[0], l.p2[1] - l.p1[1]) > 0.02;
}

export function polygonArea(poly: Point[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

export const zoneIsValid = (z: Pick<Zone, "polygon">) => z.polygon.length >= 3 && polygonArea(z.polygon) > 0.001;

/** True when a click is close enough to the first polygon point to close the shape. */
export function nearFirstPoint(poly: Point[], p: Point, rect: { width: number; height: number }, px = 12): boolean {
  if (poly.length < 3) return false;
  return Math.hypot((p[0] - poly[0][0]) * rect.width, (p[1] - poly[0][1]) * rect.height) <= px;
}

/** Sparse heatmap cells -> rectangles with an opacity relative to the busiest cell. */
export function heatCells(grid: [number, number], cells: Record<string, number>) {
  const max = Math.max(1, ...Object.values(cells));
  return Object.entries(cells).map(([idx, n]) => {
    const i = Number(idx);
    return { x: (i % grid[0]) / grid[0], y: Math.floor(i / grid[0]) / grid[1], w: 1 / grid[0], h: 1 / grid[1], opacity: n / max, count: n };
  });
}
