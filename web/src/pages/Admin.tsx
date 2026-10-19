import { useState } from "react";
import { api } from "../api";
import { Confirm, ErrorBox, Loading, Secret } from "../components/ui";
import { ago } from "../format";
import { useLoad } from "../hooks";
import type { DeviceRow, TenantRow } from "../types";

export function AdminTenants() {
  const tenants = useLoad(() => api.get<TenantRow[]>("/admin/tenants"), [], 20000);
  const [f, setF] = useState({ name: "", owner_email: "", owner_password: "", retention_days: 7 });
  const [error, setError] = useState<string | null>(null);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/admin/tenants", f);
      setF({ name: "", owner_email: "", owner_password: "", retention_days: 7 });
      void tenants.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the customer");
    }
  };
  const patch = async (id: string, body: object) => {
    setError(null);
    try {
      await api.patch(`/admin/tenants/${id}`, body);
      void tenants.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update");
    }
  };

  return (
    <>
      <header className="page-head"><h1>Customers</h1></header>
      <ErrorBox error={error ?? tenants.error} />
      {tenants.loading ? <Loading /> : (
        <div className="card table-wrap"><table>
          <thead><tr><th>Customer</th><th>Cameras</th><th>Users</th><th>Keep data (days)</th><th>Active</th></tr></thead>
          <tbody>{(tenants.data ?? []).map((t) => (
            <tr key={t.id}>
              <td>{t.name}</td><td>{t.cameras}</td><td>{t.users}</td>
              <td><input type="number" min={1} max={365} defaultValue={t.retention_days} aria-label={`Retention days for ${t.name}`}
                onBlur={(e) => { const v = Number(e.target.value); if (v !== t.retention_days) void patch(t.id, { retention_days: v }); }} /></td>
              <td><label className="inline"><input type="checkbox" checked={t.is_active} aria-label={`${t.name} active`} onChange={(e) => void patch(t.id, { is_active: e.target.checked })} /> {t.is_active ? "Active" : "Suspended"}</label></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      <form className="card form-grid" onSubmit={create} aria-label="New customer">
        <h2>New customer</h2>
        <label>Company name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>Owner email<input type="email" required value={f.owner_email} onChange={(e) => setF({ ...f, owner_email: e.target.value })} /></label>
        <label>Owner password (10+ characters)<input type="password" required minLength={10} autoComplete="new-password" value={f.owner_password} onChange={(e) => setF({ ...f, owner_password: e.target.value })} /></label>
        <label>Keep data for (days)<input type="number" min={1} max={365} value={f.retention_days} onChange={(e) => setF({ ...f, retention_days: Number(e.target.value) })} /></label>
        <div><button className="primary">Create customer</button></div>
      </form>
    </>
  );
}

export function AdminDevices() {
  const devices = useLoad(() => api.get<DeviceRow[]>("/admin/edge-devices"), [], 10000);
  const [name, setName] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.post<{ token: string }>("/admin/edge-devices", { name });
      setToken(r.token);
      setName("");
      void devices.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the device");
    }
  };
  const alive = (d: DeviceRow) => d.is_active && d.last_seen_at && Date.now() - new Date(d.last_seen_at).getTime() < 90000;

  return (
    <>
      <header className="page-head"><h1>Edge devices</h1></header>
      <p className="muted">Each Mac mini running the edge agent needs a device token. The token gives access to camera credentials, so keep it private.</p>
      <ErrorBox error={error ?? devices.error} />
      {token && <Secret label="Device token (set as AIA_EDGE_TOKEN)" value={token} />}
      {devices.loading ? <Loading /> : (
        <div className="card table-wrap"><table>
          <thead><tr><th>Name</th><th>Status</th><th>Last seen</th><th>Agent</th><th /></tr></thead>
          <tbody>{(devices.data ?? []).map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td><span className={`status ${!d.is_active ? "error" : alive(d) ? "online" : "offline"}`}><i />{!d.is_active ? "Revoked" : alive(d) ? "Connected" : "Not connected"}</span></td>
              <td>{ago(d.last_seen_at)}</td><td>{d.agent_version ?? "—"}</td>
              <td>{d.is_active && <Confirm text={`Revoke ${d.name}? The agent will stop working.`} onYes={async () => { await api.del(`/admin/edge-devices/${d.id}`); void devices.reload(); }}>Revoke</Confirm>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      <form className="card row-form" onSubmit={create} aria-label="New device">
        <input required placeholder="e.g. Office Mac mini" value={name} onChange={(e) => setName(e.target.value)} aria-label="Device name" />
        <button className="primary">Create device</button>
      </form>
    </>
  );
}
