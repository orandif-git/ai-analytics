import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Confirm, ErrorBox, Loading, Secret } from "../components/ui";
import { ago } from "../format";
import { useLoad } from "../hooks";
import type { Delivery, UserRow } from "../types";

function Webhook() {
  const hook = useLoad(() => api.get<{ url: string | null }>("/settings/webhook"), []);
  const deliveries = useLoad(() => api.get<Delivery[]>("/webhook-deliveries"), [], 8000);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.put<{ url: string; secret: string }>("/settings/webhook", { url });
      setSecret(r.secret);
      setUrl("");
      void hook.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  };

  return (
    <section className="card">
      <h2>Webhook</h2>
      <p className="muted">Alerts are sent as signed JSON to this address. Use an https URL on the public internet.</p>
      {hook.loading ? <Loading /> : <p>Current address: <code>{hook.data?.url ?? "not set"}</code></p>}
      <form onSubmit={save} className="row-form">
        <input type="url" required placeholder="https://example.com/hooks/cctv" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="Webhook URL" />
        <button className="primary">{hook.data?.url ? "Change address & new secret" : "Save"}</button>
      </form>
      <ErrorBox error={error} />
      {secret && <Secret label="Signing secret" value={secret} />}
      {hook.data?.url && (
        <div className="actions">
          <button onClick={async () => { setError(null); try { await api.post("/settings/webhook/test"); setNote("Test queued. It appears below in a few seconds."); void deliveries.reload(); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); } }}>Send test</button>
          <Confirm text="Remove the webhook? Alerts will stop." onYes={async () => { await api.del("/settings/webhook"); void hook.reload(); }}>Remove</Confirm>
        </div>
      )}
      {note && <p className="muted" role="status">{note}</p>}
      <details>
        <summary>How to verify a webhook</summary>
        <p className="muted">Each request has <code>X-AIA-Timestamp</code> and <code>X-AIA-Signature: sha256=…</code>. The signature is HMAC-SHA256 of <code>timestamp + "." + raw body</code> using your signing secret. Reject requests with an old timestamp.</p>
      </details>
      <h3>Recent deliveries</h3>
      {(deliveries.data ?? []).length === 0 ? <p className="muted">Nothing sent yet.</p> : (
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>Type</th><th>Status</th><th>Tries</th><th>Error</th></tr></thead>
          <tbody>{(deliveries.data ?? []).map((d) => (
            <tr key={d.id}><td>{ago(d.created_at)}</td><td>{d.type}</td><td><span className={`pill ${d.status}`}>{d.status}</span></td><td>{d.attempts}</td><td>{d.last_error ?? ""}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}

function Users() {
  const { me } = useAuth();
  const users = useLoad(() => api.get<UserRow[]>("/users"), []);
  const [f, setF] = useState({ email: "", password: "", role: "viewer" });
  const [error, setError] = useState<string | null>(null);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/users", f);
      setF({ email: "", password: "", role: "viewer" });
      void users.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the user");
    }
  };
  return (
    <section className="card">
      <h2>Users</h2>
      <div className="table-wrap"><table>
        <thead><tr><th>Email</th><th>Role</th><th /></tr></thead>
        <tbody>{(users.data ?? []).map((u) => (
          <tr key={u.id}><td>{u.email}</td><td>{u.role}</td>
            <td>{u.role !== "owner" && u.id !== me?.user_id && <Confirm text={`Remove ${u.email}?`} onYes={async () => { await api.del(`/users/${u.id}`); void users.reload(); }}>Remove</Confirm>}</td></tr>
        ))}</tbody>
      </table></div>
      <form onSubmit={add} className="row-form" aria-label="Add user">
        <input type="email" required placeholder="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} aria-label="New user email" />
        <input type="password" required minLength={10} placeholder="password (10+ characters)" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} aria-label="New user password" />
        <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} aria-label="Role"><option value="viewer">Viewer (read only)</option><option value="admin">Admin</option></select>
        <button className="primary">Add user</button>
      </form>
      <ErrorBox error={error ?? users.error} />
    </section>
  );
}

export function Settings() {
  const { me } = useAuth();
  return (
    <>
      <header className="page-head"><h1>Settings</h1></header>
      <section className="card">
        <h2>Your plan</h2>
        <p>Events and pictures are kept for <strong>{me?.tenant?.retention_days} days</strong>, then deleted automatically. Contact support to change this.</p>
      </section>
      <Webhook />
      <Users />
    </>
  );
}
