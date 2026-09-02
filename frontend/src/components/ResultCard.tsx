import type { AnalyzeResponse, DecisionReason, ParkingStatus } from "../types";
import { Icon } from "./Icon";

const META: Record<
  ParkingStatus,
  { cls: string; icon: "check" | "x" | "clock"; headline: string; sub: string }
> = {
  LEGAL: {
    cls: "legal",
    icon: "check",
    headline: "You can park here",
    sub: "No permit, street-cleaning, or closure conflict was found for your window.",
  },
  LEGAL_UNTIL: {
    cls: "until",
    icon: "clock",
    headline: "You can park here for now",
    sub: "Legal right now, but a verified restriction starts before you planned to leave.",
  },
  NOT_LEGAL: {
    cls: "not-legal",
    icon: "x",
    headline: "Don't park here",
    sub: "A verified restriction blocks parking here for the window you asked about.",
  },
  UNKNOWN: {
    cls: "unknown",
    icon: "clock",
    headline: "We can't verify this spot yet",
    sub: "One or more required checks couldn't be confirmed right now.",
  },
};

const CAT: Record<string, string> = {
  residential: "Permit zone",
  street_cleaning: "Street cleaning",
  temporary_closure: "Closures",
  snow_route: "Snow route",
  meter: "Meters",
};
const GLYPH: Record<string, string> = { allows: "✓", blocks: "✕", limits: "→", unknown: "?" };

function catChips(reasons: DecisionReason[]) {
  const best = new Map<string, string>();
  const rank: Record<string, number> = { blocks: 3, limits: 2, unknown: 2, allows: 1 };
  for (const r of reasons) {
    const cur = best.get(r.category);
    if (!cur || (rank[r.verdict] ?? 0) > (rank[cur] ?? 0)) best.set(r.category, r.verdict);
  }
  return [...best.entries()];
}

export function ResultCard({
  result,
  blockSummary,
}: {
  result: AnalyzeResponse;
  blockSummary?: string;
}) {
  const m = META[result.status];
  const chips = catChips(result.reasons);

  return (
    <div className={`card result ${m.cls}`}>
      <div className="status-head">
        <span className="card-title">
          <Icon name="car" className="tic" /> Parking status
        </span>
        <span className="status-updated">
          <Icon name="refresh" size={13} /> Checked just now
        </span>
      </div>

      <div className="status-panel" role="status" aria-live="polite">
        <span className="status-badge">
          <Icon name={m.icon} size={22} />
        </span>
        <div>
          <h2 className="status-headline">{m.headline}</h2>
          {result.status === "LEGAL_UNTIL" && result.move_by_display && (
            <p className="status-deadline">
              Move by <strong>{result.move_by_display}</strong>
            </p>
          )}
          <p className="status-sub">{m.sub}</p>
        </div>
      </div>

      {result.urgent_alert && result.urgent_reason && (
        <p className="status-urgent">⏰ Time-sensitive: {result.urgent_reason}</p>
      )}

      {blockSummary && <p className="status-where">{blockSummary}</p>}
      <p className="status-window">
        {result.start_time_display} → {result.end_time_display}
      </p>

      <div className="checked-for">
        <p className="cf-label">Checked for</p>
        <div className="cf-chips">
          {chips.map(([cat, verdict]) => (
            <span key={cat} className={`cf-chip ${verdict}`}>
              <span aria-hidden="true">{GLYPH[verdict] ?? "•"}</span>
              {CAT[cat] ?? cat.replace(/_/g, " ")}
            </span>
          ))}
          {result.status === "UNKNOWN" &&
            result.unknown_reasons.map((_, i) => (
              <span key={`u${i}`} className="cf-chip limits">
                <span aria-hidden="true">?</span> Not verified
              </span>
            ))}
        </div>
      </div>

      {result.core_status && result.core_status !== result.status && (
        <p className="result-changed">
          Investigation changed the deterministic result from {result.core_status} to{" "}
          {result.status}.
        </p>
      )}

      <details className="disclosure">
        <summary>View details &amp; explanation</summary>
        <ul>
          {result.status === "UNKNOWN" &&
            result.unknown_reasons.map((u, i) => (
              <li key={`u${i}`}>
                <span className="g unknown" aria-hidden="true">
                  ?
                </span>
                <span>{u}</span>
              </li>
            ))}
          {result.reasons.map((r, i) => (
            <li key={i}>
              <span className={`g ${r.verdict}`} aria-hidden="true">
                {GLYPH[r.verdict] ?? "•"}
              </span>
              <span>{r.detail}</span>
            </li>
          ))}
        </ul>
        <pre>{result.summary}</pre>
      </details>
    </div>
  );
}
