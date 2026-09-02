import { useState } from "react";
import { extendWatch, stopWatch } from "../api";
import { applyExtend, isLaterLocal } from "../monitor";
import type { ExtendWatchResponse, MonitorState } from "../types";
import { Icon } from "./Icon";

interface Props {
  monitor: MonitorState;
  onChange: (m: MonitorState | null) => void;
  onStartChanging: () => void;
  /** open straight into the extend panel (email "Extend parking time" link) */
  extendOnOpen?: boolean;
}

const STATUS_ICON: Record<string, string> = {
  LEGAL: "✅",
  LEGAL_UNTIL: "⚠️",
  NOT_LEGAL: "❌",
  UNKNOWN: "⚠️",
};

/** Persistent, compact status card for an active watch — shown on the home
 *  view before (and regardless of) any parking check. */
export function MonitorBanner({ monitor, onChange, onStartChanging, extendOnOpen }: Props) {
  const [mode, setMode] = useState<"idle" | "extend">(extendOnOpen ? "extend" : "idle");
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<ExtendWatchResponse | null>(null);

  const [d0, t0] = (monitor.endLocal ?? "T").split("T");
  const [date, setDate] = useState(d0);
  const [time, setTime] = useState(t0);

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

  const submitExtend = async () => {
    setErr(null);
    if (!date || !time) {
      setErr("Pick a new end date and time.");
      return;
    }
    const next = `${date}T${time}`;
    if (monitor.endLocal && !isLaterLocal(monitor.endLocal, next)) {
      setErr("The new end time must be later than the current one.");
      return;
    }
    setWorking(true);
    try {
      const r = await extendWatch(monitor.watchId, monitor.token, next);
      onChange(applyExtend(monitor, r)); // localStorage + card update
      setDone(r);
      setMode("idle");
    } catch (e) {
      setErr(String((e as Error).message ?? e)); // local monitor state untouched
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="card monitor">
      <div className="monitor-top">
        <span className="monitor-ic">
          <Icon name="bell" size={24} />
        </span>
        <div className="monitor-body">
          <span className="monitor-badge">Monitoring active</span>
          {monitor.locationSummary && <p className="monitor-loc">{monitor.locationSummary}</p>}
          <div className="monitor-meta">
            {monitor.throughDisplay && (
              <div>
                <Icon name="calendar" size={15} className="mm-ic" />
                Through {monitor.throughDisplay}
              </div>
            )}
            {monitor.email && (
              <div>
                <Icon name="mail" size={15} className="mm-ic" />
                <span className="muted">{monitor.email}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {done && (
        <div className="extend-done" role="status" aria-live="polite">
          <p className="mon-ok">✅ Monitoring extended</p>
          <p className="note">Now monitoring through {done.through_display}</p>
          <p>
            {STATUS_ICON[done.status] ?? ""} {done.summary}
          </p>
          {done.status === "LEGAL_UNTIL" && done.move_by_display && (
            <p>
              Move by: <strong>{done.move_by_display}</strong>
            </p>
          )}
          <button className="link" onClick={() => setDone(null)}>
            Dismiss
          </button>
        </div>
      )}

      {err && (
        <p className="mon-err" role="alert">
          {err}
        </p>
      )}

      {mode === "extend" ? (
        <div className="extend-panel">
          <p className="extend-current">
            Current end: {monitor.throughDisplay ?? monitor.endLocal ?? "—"}
          </p>
          <div className="row">
            <label>
              New end
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label>
              New end time
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </label>
          </div>
          <div className="mon-actions">
            <button className="primary" disabled={working} onClick={submitExtend}>
              {working ? "Updating…" : "Update parking time"}
            </button>
            <button
              className="link"
              onClick={() => {
                setMode("idle");
                setErr(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="monitor-actions">
          <button className="pill blue" disabled={working} onClick={onStartChanging}>
            <Icon name="route" size={16} />
            Change parking spot
          </button>
          <button
            className="pill violet"
            disabled={working || !monitor.endLocal}
            onClick={() => {
              setDone(null);
              setErr(null);
              setMode("extend");
            }}
          >
            <Icon name="clock" size={16} />
            Extend parking time
          </button>
          <button className="pill red" disabled={working} onClick={stop}>
            <Icon name="x" size={16} />
            {working ? "Stopping…" : "Stop monitoring"}
          </button>
        </div>
      )}
    </div>
  );
}
