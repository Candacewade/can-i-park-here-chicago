import { useEffect, useMemo, useState } from "react";
import { analyze, fetchLocations } from "./api";
import { AgentInspector } from "./components/AgentInspector";
import { ResultCard } from "./components/ResultCard";
import { SelectorForm } from "./components/SelectorForm";
import type { AnalyzeResponse, LocationsResponse, ParkingSelection } from "./types";
import "./styles.css";

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function defaultSelection(loc: LocationsResponse): ParkingSelection {
  const nb = loc.neighborhoods[0];
  const street = nb?.streets[0];
  const block = street?.blocks[0];
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 3600 * 1000);
  return {
    neighborhood: nb?.name ?? "",
    street_name: street?.street_name ?? "",
    from_cross_street: block?.from_cross_street ?? "",
    to_cross_street: block?.to_cross_street ?? "",
    side: block?.sides[0]?.side ?? "",
    location_id: block?.sides[0]?.location_id ?? "",
    start_date: isoDate(now),
    start_time: "19:00",
    end_date: isoDate(tomorrow),
    end_time: "09:00",
    permit_zone: "",
  };
}

export default function App() {
  const [locations, setLocations] = useState<LocationsResponse | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [selection, setSelection] = useState<ParkingSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);

  useEffect(() => {
    fetchLocations()
      .then((loc) => {
        setLocations(loc);
        setSelection(defaultSelection(loc));
      })
      .catch((e) => setLoadErr(String(e.message ?? e)));
  }, []);

  const confirmation = useMemo(() => {
    if (!selection) return null;
    return {
      block: `${selection.street_name} between ${selection.from_cross_street} and ${selection.to_cross_street}`,
      side: selection.side.toUpperCase(),
      when: `${selection.start_date} ${selection.start_time} → ${selection.end_date} ${selection.end_time}`,
      permit: selection.permit_zone.trim() ? `Zone ${selection.permit_zone.trim()}` : "No permit",
    };
  }, [selection]);

  const run = async () => {
    if (!selection) return;
    setBusy(true);
    setRunErr(null);
    setResult(null);
    try {
      setResult(await analyze(selection));
    } catch (e) {
      setRunErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header>
        <h1>Can I Park Here?</h1>
        <p className="tag">
          Chicago street parking, checked against City data. A deterministic rule
          engine decides legality; an AI agent investigates the edges and explains.
        </p>
      </header>

      {loadErr && <div className="card error">Couldn’t load locations: {loadErr}</div>}

      {locations && selection && (
        <div className="layout">
          <div>
            <SelectorForm
              locations={locations}
              value={selection}
              onChange={setSelection}
              onSubmit={run}
              busy={busy}
            />
            {confirmation && (
              <div className="card confirm">
                <h3>You selected</h3>
                <p>{confirmation.block}</p>
                <p>
                  <strong>{confirmation.side} SIDE</strong>
                </p>
                <p>{confirmation.when}</p>
                <p>{confirmation.permit}</p>
                {!locations.generated && (
                  <p className="note">
                    Pilot coverage: {locations.source}.
                  </p>
                )}
              </div>
            )}
          </div>

          <div>
            {busy && (
              <div className="card working">
                <div className="spinner" />
                <p>
                  The agent is checking City of Chicago data (permit zones, street
                  cleaning, closures{selection.start_date < "2026-04-01" ? ", snow routes" : ""}
                  …). This can take ~30 seconds.
                </p>
              </div>
            )}
            {runErr && <div className="card error">{runErr}</div>}
            {result && !busy && (
              <>
                <ResultCard result={result} />
                <AgentInspector result={result} />
              </>
            )}
          </div>
        </div>
      )}

      <footer>
        Data: City of Chicago Open Data Portal &amp; the US National Weather
        Service. Not affiliated with the City of Chicago.
      </footer>
    </div>
  );
}
