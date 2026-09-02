import { useState } from "react";
import { createWatch, replaceWatch, stopWatch } from "../api";
import type { MonitorState, WhenInput } from "../types";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface Props {
  locationId: string | null;
  blockSummary: string;
  throughDisplay: string | null;
  when: WhenInput;
  monitor: MonitorState | null;
  changing: boolean;
  onChange: (m: MonitorState | null) => void;
  onStartChanging: () => void;
  onCancelChanging: () => void;
}

export function MonitorPanel({
  locationId,
  blockSummary,
  throughDisplay,
  when,
  monitor,
  changing,
  onChange,
  onStartChanging,
  onCancelChanging,
}: Props) {
  const [phase, setPhase] = useState<"idle" | "form" | "working">("idle");
  const [email, setEmail] = useState(monitor?.email ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fail = (e: unknown) => {
    setErr(String((e as Error).message ?? e));
    setPhase("idle");
  };

  const start = async () => {
    if (!locationId) return;
    if (!EMAIL_RE.test(email.trim())) {
      setErr("Enter a valid email address.");
      return;
    }
    setErr(null);
    setPhase("working");
    try {
      const r = await createWatch({ location_id: locationId, when, email });
      onChange({
        watchId: r.watch_id,
        token: r.manage_token,
        email: email.trim(),
        locationSummary: blockSummary,
        throughDisplay: throughDisplay ?? undefined,
      });
      setPhase("idle");
      setNotice(
        r.email_registered
          ? "✅ You're all set. We'll email you if your parking status changes or you need to move your car."
          : "Monitoring is on, but we couldn't save your email yet — try again shortly.",
      );
    } catch (e) {
      fail(e);
    }
  };

  const stop = async () => {
    if (!monitor) return;
    setErr(null);
    setPhase("working");
    try {
      await stopWatch(monitor.watchId, monitor.token);
      onChange(null);
      setPhase("idle");
      setNotice("✅ Parking monitoring has been turned off.");
    } catch (e) {
      fail(e);
    }
  };

  const confirmMove = async () => {
    if (!monitor || !locationId) return;
    setErr(null);
    setPhase("working");
    try {
      const r = await replaceWatch(monitor.watchId, monitor.token, {
        location_id: locationId,
        when,
        email: monitor.email,
      });
      onChange({
        watchId: r.watch_id,
        token: r.manage_token,
        email: monitor.email,
        locationSummary: blockSummary,
        throughDisplay: throughDisplay ?? undefined,
      });
      onCancelChanging();
      setPhase("idle");
      setNotice("✅ Monitoring updated. We'll now watch your new parking location.");
    } catch (e) {
      fail(e);
    }
  };

  // --- changing an existing monitor's spot --------------------------
  if (monitor && changing) {
    return (
      <div className="card monitor">
        <h3>🔁 Change the spot you're monitoring</h3>
        {err && <p className="mon-err">{err}</p>}
        {locationId ? (
          <>
            <p>New spot:</p>
            <p className="mon-loc">{blockSummary}</p>
            {throughDisplay && <p className="note">Through {throughDisplay}</p>}
            <p className="note">
              Confirming resolves your current watch and starts a fresh one here. The
              old location stops emailing you immediately.
            </p>
            <div className="mon-actions">
              <button className="primary" disabled={phase === "working"} onClick={confirmMove}>
                {phase === "working" ? "Updating…" : "Confirm move"}
              </button>
              <button className="link" onClick={onCancelChanging}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="note">
              Enter your new address above and run the parking check, then come back
              here to confirm the move.
            </p>
            <button className="link" onClick={onCancelChanging}>
              Cancel
            </button>
          </>
        )}
      </div>
    );
  }

  // --- monitoring active -------------------------------------------
  if (monitor) {
    return (
      <div className="card monitor active">
        <h3>🔔 Monitoring active</h3>
        {notice && <p className="mon-ok">{notice}</p>}
        {err && <p className="mon-err">{err}</p>}
        {monitor.email && (
          <p>
            We'll email: <strong>{monitor.email}</strong>
          </p>
        )}
        {monitor.locationSummary && (
          <>
            <p className="note">Monitoring</p>
            <p className="mon-loc">{monitor.locationSummary}</p>
          </>
        )}
        {monitor.throughDisplay && <p className="note">Through {monitor.throughDisplay}</p>}
        <div className="mon-actions">
          <button
            className="secondary"
            disabled={phase === "working"}
            onClick={onStartChanging}
          >
            Change parking spot
          </button>
          <button className="link danger" disabled={phase === "working"} onClick={stop}>
            {phase === "working" ? "Working…" : "Stop monitoring"}
          </button>
        </div>
      </div>
    );
  }

  // --- not monitoring yet -----------------------------------------
  return (
    <div className="card monitor">
      {notice ? (
        <p className="mon-ok">{notice}</p>
      ) : phase === "form" ? (
        <>
          <h3>🔔 Monitor this parking spot</h3>
          <p className="note">
            We'll email you a morning status check and an urgent alert if you need to
            move your car. One click to stop any time.
          </p>
          <label>
            Your email
            <input
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          {err && <p className="mon-err">{err}</p>}
          <div className="mon-actions">
            <button className="primary" disabled={phase !== "form" && phase !== "idle"} onClick={start}>
              Start monitoring
            </button>
            <button
              className="link"
              onClick={() => {
                setPhase("idle");
                setErr(null);
              }}
            >
              Cancel
            </button>
          </div>
        </>
      ) : phase === "working" ? (
        <p className="note">Setting up monitoring…</p>
      ) : (
        <>
          <button
            className="secondary wide"
            disabled={!locationId}
            onClick={() => {
              setNotice(null);
              setErr(null);
              setPhase("form");
            }}
          >
            🔔 Monitor this parking spot
          </button>
          <p className="note">
            Get a daily check and urgent move-your-car alerts by email. No account
            needed.
          </p>
        </>
      )}
    </div>
  );
}
