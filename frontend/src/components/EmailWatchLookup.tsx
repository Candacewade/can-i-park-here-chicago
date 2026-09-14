import { useState } from "react";
import { Icon } from "./Icon";
import { WatchesByEmailPanel } from "./WatchesByEmailPanel";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Home-screen entry point for "find my watches": type an email, see its
 * active watches right away. NOT verified -- there's no login on this app,
 * and knowing/guessing an email used here is enough to view and cancel its
 * watches. An emailed-verification-link version was tried first and dropped
 * because the confirmation email wasn't arriving reliably; see
 * docs/monitoring.md for that trade-off. */
export function EmailWatchLookup() {
  const [phase, setPhase] = useState<"idle" | "form" | "results">("idle");
  const [input, setInput] = useState("");
  const [email, setEmail] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const submit = () => {
    const trimmed = input.trim();
    if (!EMAIL_RE.test(trimmed)) {
      setErr("Enter a valid email address.");
      return;
    }
    setErr(null);
    setEmail(trimmed);
    setPhase("results");
  };

  if (phase === "results" && email) {
    return (
      <div className="stack">
        <WatchesByEmailPanel email={email} />
        <button
          className="link"
          onClick={() => {
            setPhase("idle");
            setEmail(null);
            setInput("");
          }}
        >
          Search a different email
        </button>
      </div>
    );
  }

  if (phase === "form") {
    return (
      <div className="card monitor-cta">
        <h3>
          <Icon name="mail" size={17} /> Manage my parking watches
        </h3>
        <p className="note">See and manage every active watch for an email address.</p>
        <label>
          Your email
          <input
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        {err && (
          <p className="mon-err" role="alert">
            {err}
          </p>
        )}
        <div className="mon-actions">
          <button className="primary" onClick={submit}>
            Find my watches
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
        Already monitoring a spot from another device? Enter your email to see and manage all
        your active watches.
      </p>
    </div>
  );
}
