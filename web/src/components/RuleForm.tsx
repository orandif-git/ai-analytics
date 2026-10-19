import { useState } from "react";
import { api } from "../api";
import type { Camera, Rule, RuleKind } from "../types";
import { ErrorBox } from "./ui";

const KINDS: { value: RuleKind; label: string }[] = [
  { value: "line_cross", label: "Crosses a counting line" },
  { value: "zone_enter", label: "Enters a zone" },
  { value: "zone_dwell", label: "Stays in a zone too long" },
  { value: "zone_exit", label: "Leaves a zone" },
  { value: "detection", label: "Appears on camera" },
];

export function RuleForm({ cameras, fixedCameraId, onCreated }: { cameras: Camera[]; fixedCameraId?: string; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [cameraId, setCameraId] = useState(fixedCameraId ?? "");
  const [kind, setKind] = useState<RuleKind>("line_cross");
  const [label, setLabel] = useState("");
  const [direction, setDirection] = useState("");
  const [shapeId, setShapeId] = useState("");
  const [cooldown, setCooldown] = useState(60);
  const [error, setError] = useState<string | null>(null);

  const cam = cameras.find((c) => c.id === cameraId);
  const lines = cam?.analytics.lines ?? [];
  const zones = cam?.analytics.zones ?? [];
  const isLine = kind === "line_cross";
  const isZone = kind.startsWith("zone_");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const params: Rule["params"] = {};
      if (isLine && direction) params.direction = direction as "in" | "out";
      if (isLine && shapeId) params.line_id = shapeId;
      if (isZone && shapeId) params.zone_id = shapeId;
      await api.post("/rules", {
        name, camera_id: cameraId || null, event_kind: kind, label: label || null, params, cooldown_s: cooldown,
      });
      setName("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the rule");
    }
  };

  return (
    <form className="card form-grid" onSubmit={submit} aria-label="New rule">
      <h3>New alert rule</h3>
      <label>Name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customer entered the shop" /></label>
      {!fixedCameraId && (
        <label>Camera
          <select value={cameraId} onChange={(e) => { setCameraId(e.target.value); setShapeId(""); }}>
            <option value="">All cameras</option>
            {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      )}
      <label>When
        <select value={kind} onChange={(e) => { setKind(e.target.value as RuleKind); setShapeId(""); }}>
          {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
      </label>
      {isLine && (
        <>
          <label>Line
            <select value={shapeId} onChange={(e) => setShapeId(e.target.value)}>
              <option value="">Any line</option>
              {lines.map((l) => <option key={l.id} value={l.id}>{l.name || l.id}</option>)}
            </select>
          </label>
          <label>Direction
            <select value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="">Either way</option><option value="in">Coming IN</option><option value="out">Going OUT</option>
            </select>
          </label>
        </>
      )}
      {isZone && (
        <label>Zone
          <select value={shapeId} onChange={(e) => setShapeId(e.target.value)}>
            <option value="">Any zone</option>
            {zones.map((z) => <option key={z.id} value={z.id}>{z.name || z.id}</option>)}
          </select>
        </label>
      )}
      <label>Who
        <select value={label} onChange={(e) => setLabel(e.target.value)}>
          <option value="">Person or vehicle</option><option value="person">Person</option><option value="vehicle">Vehicle</option>
        </select>
      </label>
      <label>At most one alert every
        <span className="inline"><input type="number" min={0} max={86400} value={cooldown} onChange={(e) => setCooldown(Math.max(0, Number(e.target.value) || 0))} /> seconds</span>
      </label>
      <ErrorBox error={error} />
      <div><button className="primary">Add rule</button></div>
    </form>
  );
}
