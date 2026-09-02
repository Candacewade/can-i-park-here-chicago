import { useEffect, useMemo, useState } from "react";
import { analyze, fetchExamples, resolveAddress } from "./api";
import { AddressForm } from "./components/AddressForm";
import { AgentInspector } from "./components/AgentInspector";
import { BlockConfirm } from "./components/BlockConfirm";
import { MonitorPanel } from "./components/MonitorPanel";
import { ResultCard } from "./components/ResultCard";
import type {
  AddressInput,
  AnalyzeResponse,
  ExampleAddress,
  MonitorState,
  ResolveResponse,
  WhenInput,
} from "./types";
import "./styles.css";

const MONITOR_KEY = "ciph_monitor";

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

function loadMonitor(): MonitorState | null {
  try {
    const raw = localStorage.getItem(MONITOR_KEY);
    if (raw) return JSON.parse(raw) as MonitorState;
  } catch {
    /* private mode / blocked storage -> just no persisted monitor */
  }
  // arrived from an email "change parking spot" link?
  try {
    const q = new URLSearchParams(window.location.search);
    const watchId = q.get("manage");
    const token = q.get("token");
    if (watchId && token) return { watchId, token };
  } catch {
    /* ignore */
  }
  return null;
}

function saveMonitor(m: MonitorState | null) {
  try {
    if (m) localStorage.setItem(MONITOR_KEY, JSON.stringify(m));
    else localStorage.removeItem(MONITOR_KEY);
  } catch {
    /* best effort */
  }
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

  const [monitor, setMonitor] = useState<MonitorState | null>(() => loadMonitor());
  const [changing, setChanging] = useState<boolean>(() => {
    try {
      return new URLSearchParams(window.location.search).has("manage");
    } catch {
      return false;
    }
  });

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => setExamples([]));
    // clean the deep-link params out of the URL bar
    try {
      if (window.location.search) {
        window.history.replaceState({}, "", window.location.pathname);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const updateMonitor = (m: MonitorState | null) => {
    setMonitor(m);
    saveMonitor(m);
  };

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

  const showMonitor = (result || monitor) && !analyzing && !resolving;

  return (
    <div className="page">
      <header>
        <h1>Can I Park Here?</h1>
        <p className="tag">
          Chicago street parking, checked against City data. A deterministic rule
          engine decides legality; an AI agent investigates the edges and explains.
        </p>
      </header>

      {monitor && changing && !resolved && (
        <div className="card banner">
          You're changing your monitored parking spot. Enter the new address below,
          run the check, then confirm the move.
        </div>
      )}

      <div className="layout">
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

        <div>
          {(resolving || analyzing) && (
            <div className="card working">
              <div className="spinner" />
              <p>
                {resolving
                  ? "Resolving the address against City of Chicago street geometry…"
                  : "The agent is checking City data (permit zones, street cleaning, closures, snow routes)…"}
              </p>
            </div>
          )}
          {err && <div className="card error">{err}</div>}
          {result && !analyzing && (
            <>
              <ResultCard result={result} />
              <AgentInspector result={result} />
            </>
          )}
          {showMonitor && (
            <MonitorPanel
              locationId={locationId}
              blockSummary={blockSummary}
              throughDisplay={result?.end_time_display ?? null}
              when={when}
              monitor={monitor}
              changing={changing}
              onChange={updateMonitor}
              onStartChanging={() => {
                setChanging(true);
                setResolved(null);
                setResult(null);
              }}
              onCancelChanging={() => setChanging(false)}
            />
          )}
        </div>
      </div>

      <footer>
        Data: City of Chicago Open Data Portal, US Census Bureau geocoder &amp; the
        US National Weather Service. Not affiliated with the City of Chicago.
      </footer>
    </div>
  );
}
