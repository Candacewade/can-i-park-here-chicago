import { useState } from "react";
import { stopWatch } from "../api";
import type { MonitorState } from "../types";

interface Props {
  monitor: MonitorState;
  onChange: (m: MonitorState | null) => void;
  onStartChanging: () => void;
}

/** Persistent, always-visible card for an active watch — shown on the home
 *  view before (and regardless of) any parking check. */
export function MonitorBanner({ monitor, onChange, onStartChanging }: Props) {
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const stop = async () => {
    setErr(null);
    setWorking(true);
    try {
      await stopWatch(monitor.watchId, monitor.token);
      onChange(null);
    } catch (e) {
      setErr(String((e as Error).message ?? e));
      setWorking(false);
    }
  };

  return (
    <div className="card monitor-banner">
      <div className="mb-main">
        <div className="mb-title">🔔 Monitoring active</div>
        {monitor.locationSummary && <div className="mb-loc">{monitor.locationSummary}</div>}
        {monitor.throughDisplay && (
          <div className="note">Through {monitor.throughDisplay}</div>
        )}
        {monitor.email && (
          <div className="note">
            Emailing <strong>{monitor.email}</strong>
          </div>
        )}
        {err && <div className="mon-err">{err}</div>}
      </div>
      <div className="mb-actions">
        <button className="secondary" disabled={working} onClick={onStartChanging}>
          Change parking spot
        </button>
        <button className="link danger" disabled={working} onClick={stop}>
          {working ? "Stopping…" : "Stop monitoring"}
        </button>
      </div>
    </div>
  );
}
