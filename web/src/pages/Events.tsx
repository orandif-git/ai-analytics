import { useMemo, useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading } from "../components/ui";
import { describe, kindLabel, when, type ShapeNames } from "../format";
import { useImage, useLoad } from "../hooks";
import type { Camera, EventKind, EventRow } from "../types";

const ACTIVITY: EventKind[] = ["detection", "line_cross", "zone_enter", "zone_exit", "zone_dwell"];

function Snapshot({ id, onClose }: { id: number; onClose: () => void }) {
  const url = useImage(`/events/${id}/snapshot`);
  return (
    <div className="modal" role="dialog" aria-label="Event snapshot" onClick={onClose}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        {url ? <img src={url} alt="Event snapshot" /> : <p className="muted">Loading…</p>}
        <button onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

export function Events() {
  const cams = useLoad(() => api.get<Camera[]>("/cameras"), []);
  const [camId, setCamId] = useState("");
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const events = useLoad(
    () => api.get<EventRow[]>(`/events?limit=200${camId ? `&camera_id=${camId}` : ""}${kind ? `&kind=${kind}` : ""}`),
    [camId, kind], 10000);

  const camName = useMemo(() => Object.fromEntries((cams.data ?? []).map((c) => [c.id, c.name])), [cams.data]);
  const names = useMemo(() => {
    const m: Record<string, ShapeNames> = {};
    for (const c of cams.data ?? []) {
      m[c.id] = {};
      for (const s of [...(c.analytics.lines ?? []), ...(c.analytics.zones ?? [])]) if (s.name) m[c.id][s.id] = s.name;
    }
    return m;
  }, [cams.data]);

  // "All activity" hides the per-minute count/heatmap summaries, which are not interesting to read one by one.
  const rows = (events.data ?? []).filter((e) => kind || ACTIVITY.includes(e.kind));

  return (
    <>
      <header className="page-head">
        <h1>Events</h1>
        <div className="controls">
          <select aria-label="Camera" value={camId} onChange={(e) => setCamId(e.target.value)}><option value="">All cameras</option>{(cams.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <select aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All activity</option>
            {ACTIVITY.map((k) => <option key={k} value={k}>{kindLabel(k)}</option>)}
            <option value="count">Counts (per minute)</option>
          </select>
        </div>
      </header>
      <ErrorBox error={events.error} />
      {events.loading ? <Loading /> : rows.length === 0 ? <Empty><p>No events yet.</p></Empty> : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Time</th><th>Camera</th><th>What happened</th><th /></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td>{when(e.ts)}</td>
                  <td>{camName[e.camera_id] ?? "—"}</td>
                  <td><span className={`pill ${e.kind}`}>{kindLabel(e.kind)}</span> {describe(e, names[e.camera_id])}</td>
                  <td>{e.has_snapshot && <button onClick={() => setOpen(e.id)}>Picture</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open !== null && <Snapshot id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
