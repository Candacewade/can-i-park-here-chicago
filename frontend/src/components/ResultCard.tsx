import type { AnalyzeResponse, ParkingStatus } from "../types";

const META: Record<ParkingStatus, { cls: string; icon: string; headline: string }> = {
  LEGAL: { cls: "legal", icon: "✅", headline: "You can park here" },
  LEGAL_UNTIL: { cls: "until", icon: "⚠️", headline: "You can park here for now" },
  NOT_LEGAL: { cls: "not-legal", icon: "❌", headline: "Don't park here" },
  UNKNOWN: { cls: "unknown", icon: "⚠️", headline: "We can't verify this spot yet" },
};

const GLYPH: Record<string, string> = { allows: "✓", blocks: "✕", limits: "→", unknown: "?" };

export function ResultCard({
  result,
  blockSummary,
}: {
  result: AnalyzeResponse;
  blockSummary?: string;
}) {
  const m = META[result.status];

  return (
    <div className={`card result ${m.cls}`} role="status" aria-live="polite">
      <div className="result-status">
        <span className="result-icon" aria-hidden="true">
          {m.icon}
        </span>
        <div>
          <h2 className="result-headline">{m.headline}</h2>
          {result.status === "LEGAL_UNTIL" && result.move_by_display && (
            <p className="result-deadline">
              Move by <strong>{result.move_by_display}</strong>
            </p>
          )}
        </div>
      </div>

      {result.urgent_alert && result.urgent_reason && (
        <p className="result-urgent">⏰ Time-sensitive: {result.urgent_reason}</p>
      )}

      <div className="result-meta">
        {blockSummary && <p className="result-where">{blockSummary}</p>}
        <p className="result-window">
          {result.start_time_display} → {result.end_time_display}
        </p>
      </div>

      <ul className="result-reasons">
        {result.status === "UNKNOWN" &&
          result.unknown_reasons.map((u, i) => (
            <li key={`u${i}`}>
              <span className="glyph unknown" aria-hidden="true">
                ?
              </span>
              <span>{u}</span>
            </li>
          ))}
        {result.reasons.map((r, i) => (
          <li key={i}>
            <span className={`glyph ${r.verdict}`} aria-hidden="true">
              {GLYPH[r.verdict] ?? "•"}
            </span>
            <span>{r.detail}</span>
          </li>
        ))}
      </ul>

      {result.core_status && result.core_status !== result.status && (
        <p className="result-changed">
          Investigation changed the deterministic result from {result.core_status} to{" "}
          {result.status}.
        </p>
      )}

      <details className="disclosure">
        <summary>How we checked this</summary>
        <pre>{result.summary}</pre>
      </details>
    </div>
  );
}
