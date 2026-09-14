import { useState } from "react";
import { clearWatchOverride, setWatchOverride } from "../api";
import type { ParkingStatus, WatchOverrideView } from "../types";
import { Icon } from "./Icon";

interface Props {
  watchId: string;
  manageToken: string;
  override: WatchOverrideView | null;
  /** "YYYY-MM-DDTHH:MM" -- used to default "applies until" to the watch's own end. */
  defaultExpiresLocal?: string;
  onChange: (override: WatchOverrideView | null) => void;
}

const STATUS_OPTIONS: { value: ParkingStatus; label: string }[] = [
  { value: "NOT_LEGAL", label: "Not legal to park here" },
  { value: "LEGAL_UNTIL", label: "Legal, but I need to move by a certain time" },
  { value: "LEGAL", label: "Legal to park here" },
];

/** Report what you actually see (e.g. a posted sign that doesn't match the
 * app's data) and have it fully replace this watch's status/alerts. NOT
 * verified -- see docs/monitoring.md for what that means. Shared by
 * MonitorBanner and the "find my watches" list so both offer the same
 * report/clear controls. */
export function OverrideReport({
  watchId,
  manageToken,
  override,
  defaultExpiresLocal,
  onChange,
}: Props) {
  const [mode, setMode] = useState<"idle" | "form">("idle");
  const [status, setStatus] = useState<ParkingStatus>("NOT_LEGAL");
  const [note, setNote] = useState("");
  const [moveBy, setMoveBy] = useState("");
  const [expiresAt, setExpiresAt] = useState(defaultExpiresLocal ?? "");
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (!note.trim()) {
      setErr("Say what you saw (e.g. the sign's wording, or where it's posted).");
      return;
    }
    if (!expiresAt) {
      setErr("Pick when this report should stop applying.");
      return;
    }
    if (status === "LEGAL_UNTIL" && !moveBy) {
      setErr("Pick the time you need to move by.");
      return;
    }
    setWorking(true);
    try {
      const r = await setWatchOverride(watchId, manageToken, {
        status,
        note,
        expiresAtLocal: expiresAt,
        moveByLocal: status === "LEGAL_UNTIL" ? moveBy : undefined,
      });
      onChange(r.override);
      setMode("idle");
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setWorking(false);
    }
  };

  const clear = async () => {
    setErr(null);
    setWorking(true);
    try {
      const w = await clearWatchOverride(watchId, manageToken);
      onChange(w.override);
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setWorking(false);
    }
  };

  if (override) {
    return (
      <div className="override-active">
        <p className="override-label">
          <Icon name="ticket" size={15} className="mm-ic" />
          You reported this — not verified city data
        </p>
        <p className="note">"{override.note}"</p>
        <p className="note">Applies until {override.expires_at_local.replace("T", " ")}.</p>
        {err && (
          <p className="mon-err" role="alert">
            {err}
          </p>
        )}
        <button className="link" disabled={working} onClick={clear}>
          {working ? "Clearing…" : "Clear my report"}
        </button>
      </div>
    );
  }

  if (mode === "idle") {
    return (
      <button className="link" onClick={() => setMode("form")}>
        Report what you see (e.g. a sign that doesn't match this)
      </button>
    );
  }

  return (
    <div className="override-form">
      <label>
        What's actually true here?
        <select value={status} onChange={(e) => setStatus(e.target.value as ParkingStatus)}>
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      {status === "LEGAL_UNTIL" && (
        <label>
          Move by
          <input type="datetime-local" value={moveBy} onChange={(e) => setMoveBy(e.target.value)} />
        </label>
      )}
      <label>
        What did you see?
        <textarea
          rows={2}
          placeholder='e.g. "Orange street cleaning sign, Thursdays 9am-2pm"'
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <label>
        Applies until
        <input
          type="datetime-local"
          value={expiresAt}
          onChange={(e) => setExpiresAt(e.target.value)}
        />
      </label>
      {err && (
        <p className="mon-err" role="alert">
          {err}
        </p>
      )}
      <div className="mon-actions">
        <button className="primary" disabled={working} onClick={submit}>
          {working ? "Saving…" : "Save my report"}
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
  );
}
