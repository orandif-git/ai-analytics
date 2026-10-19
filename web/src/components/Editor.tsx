import { useEffect, useRef, useState } from "react";
import { inDirection, lineIsValid, midpoint, nearFirstPoint, nextId, toNormalized, zoneIsValid } from "../geometry";
import type { Analytics, Line, Point, Zone } from "../types";

type Tool = "select" | "line" | "zone";
interface Props {
  image: string | null;
  value: Analytics;
  onChange: (a: Analytics) => void;
  readOnly?: boolean;
}

const pct = (v: number) => `${v * 100}%`;

/** Draw counting lines and zones on top of a camera picture. Everything is stored as 0-1 coordinates. */
export function Editor({ image, value, onChange, readOnly }: Props) {
  const [tool, setTool] = useState<Tool>("select");
  const [p1, setP1] = useState<Point | null>(null);
  const [poly, setPoly] = useState<Point[]>([]);
  const [hover, setHover] = useState<Point | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const cancel = () => {
    setP1(null);
    setPoly([]);
    setNote(null);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && cancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const rect = () => box.current!.getBoundingClientRect();
  const point = (e: React.MouseEvent) => toNormalized(e.clientX, e.clientY, rect());

  const finishZone = (points: Point[]) => {
    const zone: Zone = { id: nextId("zone", value.zones), name: null, polygon: points, dwell_s: 30 };
    if (!zoneIsValid(zone)) {
      setNote("That zone is too small or flat. Click at least three corners that enclose an area.");
      return;
    }
    onChange({ ...value, zones: [...value.zones, zone] });
    cancel();
    setTool("select");
  };

  const click = (e: React.MouseEvent) => {
    if (readOnly || tool === "select") return;
    const p = point(e);
    setNote(null);
    if (tool === "line") {
      if (!p1) return setP1(p);
      const line: Line = { id: nextId("line", value.lines), name: null, p1, p2: p, in_side: "left" };
      if (!lineIsValid(line)) return setNote("Pick a second point further from the first.");
      onChange({ ...value, lines: [...value.lines, line] });
      cancel();
      setTool("select");
    } else {
      if (nearFirstPoint(poly, p, rect())) return finishZone(poly);
      setPoly([...poly, p]);
    }
  };

  const setLine = (id: string, patch: Partial<Line>) =>
    onChange({ ...value, lines: value.lines.map((l) => (l.id === id ? { ...l, ...patch } : l)) });
  const setZone = (id: string, patch: Partial<Zone>) =>
    onChange({ ...value, zones: value.zones.map((z) => (z.id === id ? { ...z, ...patch } : z)) });

  const hint =
    tool === "line" ? (p1 ? "Click the second end of the line." : "Click the first end of the line.")
    : tool === "zone" ? (poly.length < 3 ? "Click the corners of the zone." : "Click the first point (or press Finish) to close the zone.")
    : "Choose a tool to draw a counting line or a zone.";

  return (
    <div className="editor">
      {!readOnly && (
        <div className="toolbar" role="toolbar" aria-label="Drawing tools">
          <button className={tool === "line" ? "tool active" : "tool"} onClick={() => { cancel(); setTool("line"); }}>Draw counting line</button>
          <button className={tool === "zone" ? "tool active" : "tool"} onClick={() => { cancel(); setTool("zone"); }}>Draw zone</button>
          {tool === "zone" && poly.length >= 3 && <button className="tool" onClick={() => finishZone(poly)}>Finish zone</button>}
          {tool !== "select" && <button className="tool" onClick={() => { cancel(); setTool("select"); }}>Cancel</button>}
          <span className="hint" aria-live="polite">{note ?? hint}</span>
        </div>
      )}

      <div className="canvas-wrap">
        <div
          ref={box}
          className={`canvas ${tool !== "select" && !readOnly ? "drawing" : ""}`}
          onClick={click}
          onMouseMove={(e) => (p1 || poly.length) && setHover(point(e))}
          data-testid="canvas"
        >
          {image ? <img src={image} alt="Camera preview" draggable={false} /> : <div className="placeholder">No picture yet</div>}
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="overlay">
            {value.zones.map((z) => (
              <polygon key={z.id} points={z.polygon.map((p) => p.join(",")).join(" ")} className="zone" />
            ))}
            {value.lines.map((l) => (
              <line key={l.id} x1={l.p1[0]} y1={l.p1[1]} x2={l.p2[0]} y2={l.p2[1]} className="line" />
            ))}
            {p1 && hover && <line x1={p1[0]} y1={p1[1]} x2={hover[0]} y2={hover[1]} className="line draft" />}
            {poly.length > 0 && (
              <polyline points={[...poly, ...(hover ? [hover] : [])].map((p) => p.join(",")).join(" ")} className="zone draft" />
            )}
          </svg>
          {value.lines.map((l) => {
            const m = midpoint(l.p1, l.p2);
            const d = inDirection(l);
            return (
              <span key={l.id}>
                <span className="tag" style={{ left: pct(m[0]), top: pct(m[1]) }}>{l.name || l.id}</span>
                <span className="in-dot" title="People moving toward this dot are counted as IN" style={{ left: pct(m[0] + d[0] * 0.06), top: pct(m[1] + d[1] * 0.06) }}>IN</span>
              </span>
            );
          })}
          {value.zones.map((z) => (
            <span key={z.id} className="tag zone-tag" style={{ left: pct(z.polygon[0][0]), top: pct(z.polygon[0][1]) }}>{z.name || z.id}</span>
          ))}
          {(p1 ? [p1] : poly).map((p, i) => <span key={i} className="vertex" style={{ left: pct(p[0]), top: pct(p[1]) }} />)}
        </div>
      </div>

      {(value.lines.length > 0 || value.zones.length > 0) && (
        <div className="shapes">
          {value.lines.map((l) => (
            <div className="shape" key={l.id}>
              <strong>Line</strong>
              <input aria-label={`Name of ${l.id}`} placeholder={l.id} value={l.name ?? ""} disabled={readOnly} onChange={(e) => setLine(l.id, { name: e.target.value || null })} />
              <button disabled={readOnly} onClick={() => setLine(l.id, { in_side: l.in_side === "left" ? "right" : "left" })}>Flip IN / OUT</button>
              <button className="danger" disabled={readOnly} onClick={() => onChange({ ...value, lines: value.lines.filter((x) => x.id !== l.id) })}>Delete</button>
            </div>
          ))}
          {value.zones.map((z) => (
            <div className="shape" key={z.id}>
              <strong>Zone</strong>
              <input aria-label={`Name of ${z.id}`} placeholder={z.id} value={z.name ?? ""} disabled={readOnly} onChange={(e) => setZone(z.id, { name: e.target.value || null })} />
              <label className="inline">Alert after
                <input type="number" min={1} max={86400} value={z.dwell_s} disabled={readOnly} aria-label={`Dwell seconds for ${z.id}`}
                  onChange={(e) => setZone(z.id, { dwell_s: Math.max(1, Number(e.target.value) || 1) })} /> s
              </label>
              <button className="danger" disabled={readOnly} onClick={() => onChange({ ...value, zones: value.zones.filter((x) => x.id !== z.id) })}>Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
