import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { BarChart, Empty, ErrorBox, Loading } from "../components/ui";
import { heatCells } from "../geometry";
import { useImage, useLoad } from "../hooks";
import type { Camera, Heatmap, VisitorBucket } from "../types";

export function Dashboard() {
  const cams = useLoad(() => api.get<Camera[]>("/cameras"), [], 30000);
  const [camId, setCamId] = useState("");
  const [range, setRange] = useState<"24h" | "7d">("24h");
  const cameras = cams.data ?? [];
  const cam = cameras.find((c) => c.id === camId) ?? cameras[0];

  const since = () => new Date(Date.now() - (range === "24h" ? 24 : 24 * 7) * 3600 * 1000).toISOString();
  const visitors = useLoad(
    () => (cam ? api.get<VisitorBucket[]>(`/analytics/visitors?camera_id=${cam.id}&since=${encodeURIComponent(since())}&bucket=${range === "24h" ? "hour" : "day"}`) : Promise.resolve([])),
    [cam?.id, range], 30000);
  const heat = useLoad(
    () => (cam ? api.get<Heatmap>(`/analytics/heatmap?camera_id=${cam.id}&since=${encodeURIComponent(since())}`) : Promise.resolve(null)),
    [cam?.id, range], 60000);
  const preview = useImage(cam?.has_preview ? `/cameras/${cam.id}/preview.jpg` : null, cam?.reference_snapshot_at);

  if (cams.loading) return <Loading />;
  if (cameras.length === 0) {
    return <Empty><h2>No cameras yet</h2><p>Add your first camera to start counting visitors.</p><Link className="button primary" to="/cameras">Add a camera</Link></Empty>;
  }

  const v = visitors.data ?? [];
  const entered = v.reduce((a, b) => a + b.entered, 0);
  const exited = v.reduce((a, b) => a + b.exited, 0);
  const online = cameras.filter((c) => c.status === "online").length;
  const cells = heat.data?.grid ? heatCells(heat.data.grid, heat.data.cells) : [];
  const hasLine = (cam?.analytics.lines ?? []).length > 0;

  return (
    <>
      <header className="page-head">
        <h1>Dashboard</h1>
        <div className="controls">
          <select aria-label="Camera" value={cam?.id} onChange={(e) => setCamId(e.target.value)}>{cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <select aria-label="Period" value={range} onChange={(e) => setRange(e.target.value as "24h" | "7d")}><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option></select>
        </div>
      </header>
      <ErrorBox error={cams.error ?? visitors.error ?? heat.error} />
      <div className="tiles">
        <div className="tile"><span>Visitors in</span><strong data-testid="total-in">{entered}</strong></div>
        <div className="tile"><span>Visitors out</span><strong data-testid="total-out">{exited}</strong></div>
        <div className="tile"><span>Cameras online</span><strong>{online} / {cameras.length}</strong></div>
      </div>
      <section className="card">
        <h2>Visitors over time</h2>
        {!hasLine && <p className="muted">Draw a counting line on this camera to count visitors. <Link to={`/cameras/${cam?.id}`}>Open camera</Link></p>}
        {v.length === 0 ? <p className="muted">No crossings recorded in this period.</p> : (
          <BarChart data={v.map((b) => ({ label: new Date(b.bucket).toLocaleString([], range === "24h" ? { hour: "2-digit", minute: "2-digit" } : { weekday: "short", day: "numeric" }), a: b.entered, b: b.exited }))} />
        )}
      </section>
      <section className="card">
        <h2>Where people stand (heatmap)</h2>
        {cells.length === 0 ? <p className="muted">No heatmap data in this period yet.</p> : (
          <div className="canvas-wrap"><div className="canvas" data-testid="heatmap">
            {preview ? <img src={preview} alt="Camera preview" /> : <div className="placeholder">No picture yet</div>}
            <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="overlay">
              {cells.map((c, i) => <rect key={i} x={c.x} y={c.y} width={c.w} height={c.h} fill={`hsl(${Math.round(55 - 55 * c.opacity)} 95% 50%)`} fillOpacity={0.35 + c.opacity * 0.5} stroke="#fff" strokeOpacity={0.6} strokeWidth={1} vectorEffect="non-scaling-stroke"><title>{`${c.count} sightings`}</title></rect>)}
            </svg>
          </div></div>
        )}
      </section>
    </>
  );
}
