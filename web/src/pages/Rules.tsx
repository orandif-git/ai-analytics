import { Link } from "react-router-dom";
import { api } from "../api";
import { RuleForm } from "../components/RuleForm";
import { Confirm, Empty, ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";
import type { Camera, Rule } from "../types";

const KIND: Record<string, string> = {
  line_cross: "crosses a line", zone_enter: "enters a zone", zone_dwell: "stays in a zone", zone_exit: "leaves a zone", detection: "appears",
};

export function Rules() {
  const rules = useLoad(() => api.get<Rule[]>("/rules"), []);
  const cams = useLoad(() => api.get<Camera[]>("/cameras"), []);
  const hook = useLoad(() => api.get<{ url: string | null }>("/settings/webhook"), []);
  if (rules.loading || cams.loading) return <Loading />;
  const camName = (id: string | null) => (id ? cams.data?.find((c) => c.id === id)?.name ?? "?" : "All cameras");
  // Show the name the user gave the line/zone, not its internal id.
  const shapeName = (r: Rule) => {
    const id = r.params.line_id ?? r.params.zone_id;
    if (!id) return null;
    const a = cams.data?.find((c) => c.id === r.camera_id)?.analytics;
    return [...(a?.lines ?? []), ...(a?.zones ?? [])].find((s) => s.id === id)?.name || id;
  };

  return (
    <>
      <header className="page-head"><h1>Rules & alerts</h1></header>
      <ErrorBox error={rules.error ?? cams.error ?? hook.error} />
      {!hook.loading && !hook.data?.url && (
        <div className="notice warn" role="alert">No webhook is set up, so rules cannot send alerts yet. <Link to="/settings">Set up your webhook</Link></div>
      )}
      {(rules.data ?? []).length === 0 ? <Empty><p>No rules yet. A rule sends a webhook to your system when something happens.</p></Empty> : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Rule</th><th>Camera</th><th>When</th><th>Limit</th><th /></tr></thead>
            <tbody>
              {(rules.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td><td>{camName(r.camera_id)}</td>
                  <td>{r.label ?? "Someone"} {KIND[r.event_kind]}{r.params.direction ? ` (${r.params.direction})` : ""}{shapeName(r) ? ` · ${shapeName(r)}` : ""}</td>
                  <td>1 per {r.cooldown_s}s</td>
                  <td className="actions">
                    <label className="inline"><input type="checkbox" checked={r.enabled} aria-label={`Enable ${r.name}`} onChange={async (e) => { await api.patch(`/rules/${r.id}`, { enabled: e.target.checked }); void rules.reload(); }} /> On</label>
                    <Confirm text={`Delete rule "${r.name}"?`} onYes={async () => { await api.del(`/rules/${r.id}`); void rules.reload(); }}>Delete</Confirm>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <RuleForm cameras={cams.data ?? []} onCreated={() => void rules.reload()} />
    </>
  );
}
