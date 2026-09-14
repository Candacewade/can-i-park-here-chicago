import { useEffect, useState } from "react";
import { extendWatch, listWatchesByEmail, stopWatch } from "../api";
import { isLaterLocal } from "../monitor";
import type { WatchListItem } from "../types";
import { Icon } from "./Icon";

interface Props {
  email: string;
}

const STATUS_ICON: Record<string, string> = {
  LEGAL: "✅",
  LEGAL_UNTIL: "⚠️",
  NOT_LEGAL: "❌",
  UNKNOWN: "⚠️",
};

function WatchRow({ watch, onRemoved }: { watch: WatchListItem; onRemoved: () => void }) {
  const [current, setCurrent] = useState(watch);
  const [mode, setMode] = useState<"idle" | "extend">("idle");
  const [working, setWorking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const [d0, t0] = (current.end_time_local ?? "T").split("T");
  const [date, setDate] = useState(d0);
  const [time, setTime] = useState(t0);

  const stop = async () => {
    setErr(null);
    setWorking(true);
    try {
      await stopWatch(current.watch_id, current.manage_token);
      onRemoved();
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
    if (current.end_time_local && !isLaterLocal(current.end_time_local, next)) {
      setErr("The new end time must be later than the current one.");
      return;
    }
    setWorking(true);
    try {
      const r = await extendWatch(current.watch_id, current.manage_token, next);
      setCurrent({
        ...current,
        through_display: r.through_display,
        end_time_local: r.end_time_local,
        status: r.status,
      });
      setMode("idle");
      setDone(true);
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="card monitor">
      <div className="monitor-top">
        <span className="monitor-ic">{STATUS_ICON[current.status.toUpperCase()] ?? "🔔"}</span>
        <div className="monitor-body">
          {current.location_summary && <p className="monitor-loc">{current.location_summary}</p>}
          <div className="monitor-meta">
            {current.through_display && (
              <div>
                <Icon name="calendar" size={15} className="mm-ic" />
                Through {current.through_display}
              </div>
            )}
          </div>
        </div>
      </div>

      {done && (
        <p className="mon-ok" role="status">
          ✅ Updated — now monitoring through {current.through_display}.
        </p>
      )}
      {err && (
        <p className="mon-err" role="alert">
          {err}
        </p>
      )}

      {mode === "extend" ? (
        <div className="extend-panel">
          <p className="extend-current">
            Current end: {current.through_display ?? current.end_time_local ?? "—"}
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
          <a
            className="pill blue"
            href={`/?manage=${encodeURIComponent(current.watch_id)}&token=${encodeURIComponent(
              current.manage_token,
            )}`}
          >
            <Icon name="route" size={16} />
            Change parking spot
          </a>
          <button
            className="pill violet"
            disabled={working}
            onClick={() => {
              setDone(false);
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

/** Every active watch registered to this email, each independently editable.
 * NOT verified -- the address alone is enough (see EmailWatchLookup.tsx and
 * docs/monitoring.md for why). */
export function WatchesByEmailPanel({ email }: Props) {
  const [watches, setWatches] = useState<WatchListItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listWatchesByEmail(email)
      .then((w) => {
        if (!cancelled) setWatches(w);
      })
      .catch((e) => {
        if (!cancelled) setErr(String((e as Error).message ?? e));
      });
    return () => {
      cancelled = true;
    };
  }, [email]);

  if (err) {
    return (
      <div className="callout warn" role="alert">
        ⚠️ Couldn't look up watches for that address: {err}
      </div>
    );
  }
  if (watches === null) {
    return (
      <div className="card working" role="status" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Loading your parking watches…</p>
      </div>
    );
  }
  if (watches.length === 0) {
    return (
      <div className="card">
        <h3>Your parking watches</h3>
        <p className="note">No active parking watches for this email address right now.</p>
      </div>
    );
  }
  return (
    <div className="stack">
      <h2>Your parking watches</h2>
      {watches.map((w) => (
        <WatchRow
          key={w.watch_id}
          watch={w}
          onRemoved={() =>
            setWatches((cur) => (cur ?? []).filter((x) => x.watch_id !== w.watch_id))
          }
        />
      ))}
    </div>
  );
}
