import type { AnalyzeResponse, ParkingStatus } from "../types";

const META: Record<ParkingStatus, { cls: string; icon: string; label: string }> = {
  LEGAL: { cls: "legal", icon: "✅", label: "Parking allowed" },
  LEGAL_UNTIL: { cls: "until", icon: "⚠️", label: "Allowed — but you must move" },
  NOT_LEGAL: { cls: "not-legal", icon: "🚫", label: "Do not park here" },
  UNKNOWN: { cls: "unknown", icon: "❓", label: "Could not verify" },
};

export function ResultCard({ result }: { result: AnalyzeResponse }) {
  const m = META[result.status];
  return (
    <div className={`card result ${m.cls}`}>
      <div className="result-head">
        <span className="result-icon">{m.icon}</span>
        <div>
          <div className="result-label">{m.label}</div>
          {result.status === "LEGAL_UNTIL" && result.move_by_display && (
            <div className="result-moveby">Move by {result.move_by_display}</div>
          )}
        </div>
      </div>

      {result.urgent_alert && (
        <div className="urgent">⏰ Time-sensitive: {result.urgent_reason}</div>
      )}

      <div className="interval">
        {result.start_time_display} → {result.end_time_display}
      </div>

      {result.status === "UNKNOWN" && result.unknown_reasons.length > 0 && (
        <ul className="reasons">
          {result.unknown_reasons.map((u, i) => (
            <li key={i} className="r-unknown">{u}</li>
          ))}
        </ul>
      )}

      <ul className="reasons">
        {result.reasons.map((r, i) => (
          <li key={i} className={`r-${r.verdict}`}>
            <strong>{r.category.replace(/_/g, " ")}:</strong> {r.detail}
          </li>
        ))}
      </ul>

      {result.core_status && result.core_status !== result.status && (
        <p className="note">
          Investigation changed the deterministic result from {result.core_status} to{" "}
          {result.status}.
        </p>
      )}

      <div className="summary">
        <h3>Explanation</h3>
        <pre>{result.summary}</pre>
      </div>
    </div>
  );
}
