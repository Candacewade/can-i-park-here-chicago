import { useEffect, useMemo, useRef, useState } from "react";
import { analyze, fetchExamples, getWatch, resolveAddress } from "./api";
import { AddressForm } from "./components/AddressForm";
import { AgentInspector } from "./components/AgentInspector";
import { BlockConfirm } from "./components/BlockConfirm";
import { Hero } from "./components/Hero";
import { Icon } from "./components/Icon";
import { MonitorBanner } from "./components/MonitorBanner";
import { MonitorPanel } from "./components/MonitorPanel";
import { Nav } from "./components/Nav";
import { ResultCard } from "./components/ResultCard";
import { SiteFooter } from "./components/SiteFooter";
import type { LinkStatus } from "./monitor";
import {
  loadStoredMonitor,
  needsHydration,
  readManageAction,
  readManageLink,
  resolveStartupMonitor,
  saveMonitor,
} from "./monitor";
import type {
  AddressInput,
  AnalyzeResponse,
  ExampleAddress,
  MonitorState,
  ResolveResponse,
  WhenInput,
} from "./types";
import "./styles.css";

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function defaultWhen(): WhenInput {
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 3600 * 1000);
  return {
    start_date: isoDate(now),
    start_time: "19:00",
    end_date: isoDate(tomorrow),
    end_time: "09:00",
    permit_zone: "",
  };
}

export default function App() {
  const [examples, setExamples] = useState<ExampleAddress[]>([]);
  const [address, setAddress] = useState<AddressInput>({ number: "", street: "", zip: "" });
  const [resolved, setResolved] = useState<ResolveResponse | null>(null);
  const [side, setSide] = useState("");
  const [when, setWhen] = useState<WhenInput>(defaultWhen());

  const [resolving, setResolving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  // Startup precedence: an explicit ?manage=&token= email link identifies the
  // watch to manage right now and wins over localStorage; otherwise restore the
  // stored active watch. A bad link never destroys a valid stored watch.
  const [monitor, setMonitor] = useState<MonitorState | null>(() => loadStoredMonitor());
  const [changing, setChanging] = useState(false);
  const [linkStatus, setLinkStatus] = useState<LinkStatus>(
    () => (readManageLink() ? "loading" : "none"),
  );
  const hadLink = useRef(!!readManageLink());
  const wantExtend = useRef(readManageAction() === "extend");

  const updateMonitor = (m: MonitorState | null) => {
    setMonitor(m);
    saveMonitor(m);
  };

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => setExamples([]));
  }, []);

  // 1. A capability link wins over localStorage: verify it, then adopt or reject.
  useEffect(() => {
    if (!hadLink.current) return;
    let cancelled = false;
    resolveStartupMonitor(getWatch).then(({ monitor: m, linkStatus: s }) => {
      if (cancelled) return;
      setMonitor(m);
      setLinkStatus(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. No link: hydrate a stored monitor that predates the display fields.
  useEffect(() => {
    if (hadLink.current || !needsHydration(monitor) || !monitor) return;
    let cancelled = false;
    getWatch(monitor.watchId, monitor.token)
      .then((w) => {
        if (cancelled) return;
        if (w.status !== "active") {
          updateMonitor(null);
          return;
        }
        updateMonitor({
          ...monitor,
          locationSummary: w.location_summary ?? monitor.locationSummary,
          throughDisplay: w.through_display ?? monitor.throughDisplay,
          endLocal: w.end_time_local ?? monitor.endLocal,
        });
      })
      .catch(() => {
        if (!cancelled) updateMonitor(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitor?.watchId, monitor?.token]);

  const locationId = useMemo(
    () => resolved?.side_options.find((o) => o.side === side)?.location_id ?? null,
    [resolved, side],
  );

  const blockSummary = useMemo(() => {
    if (!resolved) return "";
    const s = resolved.side_options.find((o) => o.side === side);
    return s?.summary ?? resolved.matched_address ?? "";
  }, [resolved, side]);

  const doResolve = async () => {
    setResolving(true);
    setErr(null);
    setResult(null);
    setResolved(null);
    try {
      const r = await resolveAddress(address);
      if (!r.in_chicago) {
        setErr(
          r.notes[0] ??
            "That address isn't inside the supported City of Chicago coverage area.",
        );
        return;
      }
      if (r.side_options.length === 0) {
        setErr(r.notes[0] ?? "Couldn't match that address to a Chicago street segment.");
        return;
      }
      setResolved(r);
      setSide(r.suggested_side ?? r.side_options[0].side);
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setResolving(false);
    }
  };

  const doAnalyze = async () => {
    if (!locationId) return;
    setAnalyzing(true);
    setErr(null);
    setResult(null);
    try {
      setResult(await analyze(locationId, when));
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setAnalyzing(false);
    }
  };

  const startChanging = () => {
    setChanging(true);
    setResolved(null);
    setResult(null);
    setErr(null);
  };

  const busy = resolving || analyzing;
  const readyToConfirmMove = !!(monitor && changing && result && locationId && !busy);

  return (
    <div className="shell">
      <Nav />
      <Hero />

      <div className="stack">
        {linkStatus === "loading" && (
          <div className="callout info">Opening your parking monitor…</div>
        )}
        {linkStatus === "resolved" && (
          <div className="callout warn" role="status">
            <span>
              🔕 That parking monitor has already been turned off — you won't get any more
              emails for it.
            </span>
            <button className="link" onClick={() => setLinkStatus("none")}>
              Dismiss
            </button>
          </div>
        )}
        {linkStatus === "invalid" && (
          <div className="callout warn" role="alert">
            <span>
              ⚠️ That management link isn't valid — it may be old. Use the link in your
              most recent parking email.
            </span>
            <button className="link" onClick={() => setLinkStatus("none")}>
              Dismiss
            </button>
          </div>
        )}

        {monitor && !changing && linkStatus !== "loading" && (
          <MonitorBanner
            monitor={monitor}
            onChange={updateMonitor}
            onStartChanging={startChanging}
            extendOnOpen={wantExtend.current}
          />
        )}

        {monitor && changing && !readyToConfirmMove && (
          <div className="callout info">
            <span>
              <strong>Changing your monitored parking spot.</strong> Enter the new address
              below and run the check — your current watch keeps running until you confirm.
            </span>
            <button className="link" onClick={() => setChanging(false)}>
              Cancel
            </button>
          </div>
        )}

        <div className="grid">
          <div>
            {!resolved ? (
              <AddressForm
                value={address}
                onChange={setAddress}
                onSubmit={doResolve}
                examples={examples}
                busy={resolving}
              />
            ) : (
              <BlockConfirm
                resolved={resolved}
                side={side}
                onSide={setSide}
                when={when}
                onWhen={setWhen}
                onSubmit={doAnalyze}
                onBack={() => {
                  setResolved(null);
                  setResult(null);
                }}
                busy={analyzing}
              />
            )}
          </div>

          <div className="stack">
            {busy && (
              <div className="card working" role="status" aria-live="polite">
                <div className="spinner" aria-hidden="true" />
                <p>
                  {resolving
                    ? "Matching the address to a Chicago street segment…"
                    : "Checking City data — permit zones, street cleaning, closures, snow routes…"}
                </p>
              </div>
            )}

            {err && (
              <div className="callout error" role="alert">
                {err}
              </div>
            )}

            {result && !analyzing && (
              <ResultCard result={result} blockSummary={blockSummary} />
            )}
            {result && !analyzing && (
              <MonitorPanel
                locationId={locationId}
                blockSummary={blockSummary}
                throughDisplay={result.end_time_display ?? null}
                when={when}
                monitor={monitor}
                changing={changing}
                onChange={updateMonitor}
                onCancelChanging={() => setChanging(false)}
              />
            )}
            {result && !analyzing && <AgentInspector result={result} />}

            {!busy && !err && !result && (
              <div className="card status-placeholder">
                <span className="card-title">
                  <Icon name="car" className="tic" /> Parking status
                </span>
                <p className="note">
                  Enter the address you're parked at and run a check — the verdict, the
                  move-by time, and what was checked will show up here.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}
