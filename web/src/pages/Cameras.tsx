import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { isTenantAdmin, useAuth } from "../auth";
import { Empty, ErrorBox, Loading, StatusDot } from "../components/ui";
import { ago } from "../format";
import { useLoad } from "../hooks";
import type { Camera, Site } from "../types";

const VENDORS = [
  { value: "dahua", label: "Dahua / Imou" }, { value: "hikvision", label: "Hikvision" }, { value: "uniview", label: "Uniview" },
  { value: "axis", label: "Axis" }, { value: "generic", label: "Other (type the path)" },
];

function AddCamera({ sites, onDone }: { sites: Site[]; onDone: () => void }) {
  const nav = useNavigate();
  const [siteId, setSiteId] = useState(sites[0]?.id ?? "");
  const [siteName, setSiteName] = useState("");
  const [f, setF] = useState({ name: "", vendor: "dahua", host: "", port: 554, channel: 1, stream: "sub", path: "", username: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | number) => setF((p) => ({ ...p, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sid = siteId || (await api.post<Site>("/sites", { name: siteName })).id;
      const cam = await api.post<Camera>("/cameras", {
        site_id: sid, name: f.name, vendor: f.vendor, host: f.host.trim(), port: f.port, channel: f.channel, stream: f.stream,
        path: f.vendor === "generic" ? f.path : null, username: f.username || null, password: f.password || null,
      });
      onDone();
      nav(`/cameras/${cam.id}?new=1`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the camera");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card form-grid" onSubmit={submit} aria-label="Add camera">
      <h2>Add a camera</h2>
      <p className="muted span">The camera is read by the platform's edge machine over the internet. On the site's router, forward the camera's RTSP port (usually 554) to the camera and allow only the edge machine's IP address. Use the camera's <strong>sub stream</strong>.</p>
      <label>Site
        <select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
          {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          <option value="">+ New site…</option>
        </select>
      </label>
      {!siteId && <label>New site name<input required value={siteName} onChange={(e) => setSiteName(e.target.value)} placeholder="e.g. Main store" /></label>}
      <label>Camera name<input required value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Entrance" /></label>
      <label>Brand
        <select value={f.vendor} onChange={(e) => set("vendor", e.target.value)}>{VENDORS.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select>
      </label>
      <label>Address (public IP or DDNS name)<input required value={f.host} onChange={(e) => set("host", e.target.value)} placeholder="203.0.113.10" /></label>
      <label>RTSP port<input type="number" min={1} max={65535} value={f.port} onChange={(e) => set("port", Number(e.target.value))} /></label>
      {f.vendor !== "generic" && f.vendor !== "axis" && <label>Channel<input type="number" min={1} value={f.channel} onChange={(e) => set("channel", Number(e.target.value))} /></label>}
      {f.vendor === "generic" && <label>Stream path<input required value={f.path} onChange={(e) => set("path", e.target.value)} placeholder="/stream1" /></label>}
      <label>Stream
        <select value={f.stream} onChange={(e) => set("stream", e.target.value)}><option value="sub">Sub stream (recommended)</option><option value="main">Main stream (heavy)</option></select>
      </label>
      <label>Camera username<input autoComplete="off" value={f.username} onChange={(e) => set("username", e.target.value)} /></label>
      <label>Camera password<input type="password" autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} /></label>
      <ErrorBox error={error} />
      <div><button className="primary" disabled={busy}>{busy ? "Adding…" : "Add camera"}</button></div>
    </form>
  );
}

export function Cameras() {
  const { me } = useAuth();
  const admin = isTenantAdmin(me);
  const cams = useLoad(() => api.get<Camera[]>("/cameras"), [], 10000);
  const sites = useLoad(() => api.get<Site[]>("/sites"), []);
  const [adding, setAdding] = useState(false);

  if (cams.loading || sites.loading) return <Loading />;
  const list = cams.data ?? [];
  const siteName = (id: string) => sites.data?.find((s) => s.id === id)?.name ?? "";

  return (
    <>
      <header className="page-head"><h1>Cameras</h1>{admin && !adding && <button className="primary" onClick={() => setAdding(true)}>Add camera</button>}</header>
      <ErrorBox error={cams.error ?? sites.error} />
      {adding && <AddCamera sites={sites.data ?? []} onDone={() => { void cams.reload(); }} />}
      {list.length === 0 && !adding ? <Empty><h2>No cameras yet</h2><p>{admin ? "Add a camera to get started." : "Ask an administrator to add cameras."}</p></Empty> : (
        <div className="grid">
          {list.map((c) => (
            <Link key={c.id} to={`/cameras/${c.id}`} className="card cam-card">
              <div className="row"><strong>{c.name}</strong><StatusDot status={c.status} /></div>
              <div className="muted">{siteName(c.site_id)} · {c.vendor} · {c.host}:{c.port}</div>
              <div className="muted">{c.status === "online" && c.fps ? `${c.fps.toFixed(1)} fps · ` : ""}seen {ago(c.status_at)}</div>
              <div className="muted">{(c.analytics.lines?.length ?? 0)} lines · {(c.analytics.zones?.length ?? 0)} zones</div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
