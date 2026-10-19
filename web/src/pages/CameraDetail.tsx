import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { isTenantAdmin, useAuth } from "../auth";
import { Editor } from "../components/Editor";
import { RuleForm } from "../components/RuleForm";
import { Confirm, ErrorBox, Loading, StatusDot } from "../components/ui";
import { useImage, useLoad } from "../hooks";
import type { Analytics, Camera, Rule } from "../types";

const empty = (a: Partial<Analytics>): Analytics => ({ lines: a.lines ?? [], zones: a.zones ?? [] });

export function CameraDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const { me } = useAuth();
  const admin = isTenantAdmin(me);
  const cams = useLoad(() => api.get<Camera[]>("/cameras"), [], 15000);
  const rules = useLoad(() => api.get<Rule[]>("/rules"), []);
  const cam = cams.data?.find((c) => c.id === id);

  const [draft, setDraft] = useState<Analytics | null>(null);
  const [dirty, setDirty] = useState(false);
  const [version, setVersion] = useState(0);
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const asked = useRef(false);

  useEffect(() => {
    if (cam && !dirty) setDraft(empty(cam.analytics));
  }, [cam, dirty]);

  const preview = useImage(cam?.has_preview ? `/cameras/${id}/preview.jpg` : null, `${cam?.reference_snapshot_at}-${version}`);

  const refreshPreview = useCallback(async () => {
    setAsking(true);
    setError(null);
    setMessage("Asking the edge machine for a picture…");
    try {
      const { request_id } = await api.post<{ request_id: string }>(`/cameras/${id}/snapshot-request`);
      for (let i = 0; i < 45; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const st = await api.get<{ status: string; error: string | null }>(`/cameras/snapshot-requests/${request_id}`);
        if (st.status === "done") {
          setVersion((v) => v + 1);
          void cams.reload();
          setMessage(null);
          return;
        }
        if (st.status === "error") throw new Error(st.error ?? "The camera could not be reached");
      }
      throw new Error("No answer from the edge machine. Is the agent running?");
    } catch (e) {
      setMessage(null);
      setError(e instanceof Error ? e.message : "Could not get a picture");
    } finally {
      setAsking(false);
    }
  }, [id, cams]);

  useEffect(() => {
    if (params.get("new") && admin && cam && !asked.current) {
      asked.current = true;
      void refreshPreview();
    }
  }, [params, admin, cam, refreshPreview]);

  if (cams.loading) return <Loading />;
  if (!cam || !draft) return <p>Camera not found. <Link to="/cameras">Back to cameras</Link></p>;

  const save = async () => {
    setError(null);
    try {
      const saved = await api.put<Camera>(`/cameras/${id}/analytics`, draft);
      setDirty(false);
      setDraft(empty(saved.analytics));
      setMessage("Saved. The edge machine picks up changes within a minute.");
      void cams.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    }
  };

  const mine = (rules.data ?? []).filter((r) => r.camera_id === id || r.camera_id === null);

  return (
    <>
      <header className="page-head">
        <div><Link to="/cameras" className="muted">← Cameras</Link><h1>{cam.name}</h1></div>
        <div className="controls"><StatusDot status={cam.status} />{admin && <button onClick={refreshPreview} disabled={asking}>{asking ? "Getting picture…" : "Refresh picture"}</button>}</div>
      </header>
      <ErrorBox error={error ?? cams.error} />
      {message && <div className="notice" role="status">{message}</div>}

      <section className="card">
        <h2>Counting lines and zones</h2>
        <p className="muted">Draw a line across a doorway to count people coming in and out. Draw a zone to detect people entering or waiting in an area.</p>
        <Editor image={preview} value={draft} readOnly={!admin} onChange={(a) => { setDraft(a); setDirty(true); }} />
        {admin && <div className="actions"><button className="primary" disabled={!dirty} onClick={save}>Save changes</button>{dirty && <button onClick={() => { setDirty(false); setDraft(empty(cam.analytics)); }}>Discard</button>}</div>}
      </section>

      <section className="card">
        <h2>Alert rules for this camera</h2>
        {mine.length === 0 ? <p className="muted">No rules yet. Rules send a webhook when something happens.</p> : (
          <ul className="plain">{mine.map((r) => <li key={r.id}>{r.name} {r.camera_id === null && <span className="muted">(all cameras)</span>} {!r.enabled && <span className="muted">(off)</span>}</li>)}</ul>
        )}
        <p><Link to="/rules">Manage all rules</Link></p>
      </section>
      {admin && !dirty && <RuleForm cameras={cams.data ?? []} fixedCameraId={id} onCreated={() => void rules.reload()} />}
      {admin && dirty && <p className="muted">Save your lines and zones before creating a rule that uses them.</p>}

      {admin && (
        <section className="card">
          <h2>Remove camera</h2>
          <p className="muted">Deletes the camera, its events and its rules.</p>
          <Confirm text={`Delete camera "${cam.name}"?`} onYes={async () => { await api.del(`/cameras/${id}`); nav("/cameras"); }}>Delete camera</Confirm>
        </section>
      )}
    </>
  );
}
