import { useState, type ReactNode } from "react";

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="error" role="alert">{error}</div> : null;
}

export function Loading() {
  return <p className="muted">Loading…</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function StatusDot({ status }: { status: string }) {
  const label = { online: "Online", offline: "Offline", error: "Error", unknown: "Not seen yet" }[status] ?? status;
  return <span className={`status ${status}`}><i />{label}</span>;
}

/** Shown once: API secrets and device tokens cannot be retrieved again. */
export function Secret({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="secret" role="status">
      <strong>{label}</strong>
      <p className="muted">Copy it now. It will not be shown again.</p>
      <code>{value}</code>
      <button onClick={() => navigator.clipboard?.writeText(value).then(() => setCopied(true))}>{copied ? "Copied" : "Copy"}</button>
    </div>
  );
}

export function Confirm({ text, onYes, children }: { text: string; onYes: () => void; children: ReactNode }) {
  return <button className="danger" onClick={() => window.confirm(text) && onYes()}>{children}</button>;
}

export function BarChart({ data }: { data: { label: string; a: number; b: number }[] }) {
  const max = Math.max(1, ...data.flatMap((d) => [d.a, d.b]));
  // At least 12 slots so a single hour or day does not turn into two giant bars.
  const w = 100 / Math.max(12, data.length);
  return (
    <div className="chart" role="img" aria-label="Visitors entering and leaving over time">
      <svg viewBox="0 0 100 40" preserveAspectRatio="none">
        {data.map((d, i) => (
          <g key={i}>
            <rect x={i * w + w * 0.1} y={40 - (d.a / max) * 38} width={w * 0.38} height={(d.a / max) * 38} className="bar-in"><title>{`${d.label}: ${d.a} in`}</title></rect>
            <rect x={i * w + w * 0.52} y={40 - (d.b / max) * 38} width={w * 0.38} height={(d.b / max) * 38} className="bar-out"><title>{`${d.label}: ${d.b} out`}</title></rect>
          </g>
        ))}
      </svg>
      <div className="legend"><span><i className="bar-in" /> In</span><span><i className="bar-out" /> Out</span><span className="muted">peak {max}</span></div>
    </div>
  );
}
