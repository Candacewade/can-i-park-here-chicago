import { useState } from "react";
import { createWatch, replaceWatch } from "../api";
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
  onCancelChanging: () => void;
}

/** Right-column card for the two actions tied to a parking result:
 *   - no monitor yet  -> subscribe (email -> POST /api/watches)
 *   - monitor + changing -> confirm the move to the just-checked spot
 *  The always-visible "Monitoring active" card lives in <MonitorBanner>. */
export function MonitorPanel({
  locationId,
  blockSummary,
  throughDisplay,
  when,
  monitor,
  changing,
  onChange,
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
    } catch (e) {
      fail(e);
    }
  };

  // --- confirm moving an existing monitor to the checked spot -------
  if (monitor && changing) {
    return (
      <div className="card monitor">
        <h3>🔁 Move your monitoring here?</h3>
        {err && <p className="mon-err">{err}</p>}
        <p>New spot:</p>
        <p className="mon-loc">{blockSummary}</p>
        {throughDisplay && <p className="note">Through {throughDisplay}</p>}
        <p className="note">
          Your current watch stays active until you confirm. Confirming resolves it
          and starts a fresh one here — the old location stops emailing you
          immediately.
        </p>
        <div className="mon-actions">
          <button className="primary" disabled={phase === "working"} onClick={confirmMove}>
            {phase === "working" ? "Updating…" : "Confirm move"}
          </button>
          <button className="link" onClick={onCancelChanging}>
            Keep the current spot
          </button>
        </div>
      </div>
    );
  }

  if (monitor) return null; // active card is the banner; nothing extra here

  // --- not monitoring yet: subscribe -----------------------------
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
            <button className="primary" disabled={phase !== "form"} onClick={start}>
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
