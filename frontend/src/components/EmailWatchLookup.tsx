import { useState } from "react";
import { requestWatchLookup } from "../api";
import { Icon } from "./Icon";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Home-screen entry point for "find my watches": type an email, get a link
 * mailed to it. No password on this app, so this never lists/edits anything
 * directly -- the emailed link (?manage-email=) is what proves it's really
 * you, the same trust model every other watch-management link already uses. */
export function EmailWatchLookup() {
  const [phase, setPhase] = useState<"idle" | "form" | "working" | "sent">("idle");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!EMAIL_RE.test(email.trim())) {
      setErr("Enter a valid email address.");
      return;
    }
    setErr(null);
    setPhase("working");
    try {
      await requestWatchLookup(email);
      setPhase("sent");
    } catch (e) {
      setErr(String((e as Error).message ?? e));
      setPhase("form");
    }
  };

  if (phase === "sent") {
    return (
      <div className="card monitor-cta">
        <p className="mon-ok" role="status">
          📬 Check your email — if that address has any active parking watches, we've sent a
          link to view and manage them. The link works for about 15 minutes.
        </p>
        <button
          className="link"
          onClick={() => {
            setPhase("idle");
            setEmail("");
          }}
        >
          Done
        </button>
      </div>
    );
  }

  if (phase === "form" || phase === "working") {
    return (
      <div className="card monitor-cta">
        <h3>
          <Icon name="mail" size={17} /> Manage my parking watches
        </h3>
        <p className="note">
          We'll email you a secure link to view and manage every active watch for that
          address.
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
        {err && (
          <p className="mon-err" role="alert">
            {err}
          </p>
        )}
        <div className="mon-actions">
          <button className="primary" disabled={phase === "working"} onClick={submit}>
            {phase === "working" ? "Sending…" : "Email me the link"}
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
      </div>
    );
  }

  return (
    <div className="card monitor-cta">
      <button className="secondary wide" onClick={() => setPhase("form")}>
        <Icon name="mail" size={16} /> Manage my parking watches
      </button>
      <p className="note">
        Already monitoring a spot from another device? Enter your email to get a link to
        view and manage all your active watches.
      </p>
    </div>
  );
}
