import { useMemo } from "react";
import type { LocationsResponse, ParkingSelection } from "../types";

interface Props {
  locations: LocationsResponse;
  value: ParkingSelection;
  onChange: (next: ParkingSelection) => void;
  onSubmit: () => void;
  busy: boolean;
}

const SIDE_LABEL: Record<string, string> = {
  north: "North", south: "South", east: "East", west: "West",
};

export function SelectorForm({ locations, value, onChange, onSubmit, busy }: Props) {
  const set = (patch: Partial<ParkingSelection>) => onChange({ ...value, ...patch });

  const nb = useMemo(
    () => locations.neighborhoods.find((n) => n.name === value.neighborhood),
    [locations, value.neighborhood],
  );
  const street = useMemo(
    () => nb?.streets.find((s) => s.street_name === value.street_name),
    [nb, value.street_name],
  );
  const block = useMemo(
    () =>
      street?.blocks.find(
        (b) =>
          b.from_cross_street === value.from_cross_street &&
          b.to_cross_street === value.to_cross_street,
      ),
    [street, value.from_cross_street, value.to_cross_street],
  );

  const pickNeighborhood = (name: string) => {
    const first = locations.neighborhoods.find((n) => n.name === name)?.streets[0];
    pickStreet(name, first?.street_name ?? "");
  };
  const pickStreet = (neighborhood: string, street_name: string) => {
    const s = locations.neighborhoods
      .find((n) => n.name === neighborhood)
      ?.streets.find((x) => x.street_name === street_name);
    const b = s?.blocks[0];
    set({
      neighborhood,
      street_name,
      from_cross_street: b?.from_cross_street ?? "",
      to_cross_street: b?.to_cross_street ?? "",
      side: b?.sides[0]?.side ?? "",
      location_id: b?.sides[0]?.location_id ?? "",
    });
  };
  const pickBlock = (idx: number) => {
    const b = street?.blocks[idx];
    if (!b) return;
    set({
      from_cross_street: b.from_cross_street,
      to_cross_street: b.to_cross_street,
      side: b.sides[0]?.side ?? "",
      location_id: b.sides[0]?.location_id ?? "",
    });
  };
  const pickSide = (side: string) => {
    const s = block?.sides.find((x) => x.side === side);
    if (s) set({ side, location_id: s.location_id });
  };

  const ready =
    value.location_id &&
    value.start_date &&
    value.start_time &&
    value.end_date &&
    value.end_time;

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) onSubmit();
      }}
    >
      <h2>Where are you parking?</h2>

      <label>
        Neighborhood
        <select value={value.neighborhood} onChange={(e) => pickNeighborhood(e.target.value)}>
          {locations.neighborhoods.map((n) => (
            <option key={n.name}>{n.name}</option>
          ))}
        </select>
      </label>

      <label>
        Street
        <select
          value={value.street_name}
          onChange={(e) => pickStreet(value.neighborhood, e.target.value)}
        >
          {nb?.streets.map((s) => (
            <option key={s.street_name}>{s.street_name}</option>
          ))}
        </select>
      </label>

      <label>
        Block
        <select
          value={street?.blocks.findIndex(
            (b) =>
              b.from_cross_street === value.from_cross_street &&
              b.to_cross_street === value.to_cross_street,
          )}
          onChange={(e) => pickBlock(Number(e.target.value))}
        >
          {street?.blocks.map((b, i) => (
            <option key={i} value={i}>
              {b.from_cross_street} → {b.to_cross_street}
            </option>
          ))}
        </select>
      </label>

      <div className="field">
        <span>Side of street</span>
        <div className="segmented">
          {block?.sides.map((s) => (
            <button
              type="button"
              key={s.side}
              className={value.side === s.side ? "on" : ""}
              onClick={() => pickSide(s.side)}
            >
              {SIDE_LABEL[s.side] ?? s.side}
            </button>
          ))}
        </div>
      </div>

      <h2>When?</h2>
      <div className="row">
        <label>
          Start
          <input
            type="date"
            value={value.start_date}
            onChange={(e) => set({ start_date: e.target.value })}
          />
        </label>
        <label>
          &nbsp;
          <input
            type="time"
            value={value.start_time}
            onChange={(e) => set({ start_time: e.target.value })}
          />
        </label>
      </div>
      <div className="row">
        <label>
          End
          <input
            type="date"
            value={value.end_date}
            onChange={(e) => set({ end_date: e.target.value })}
          />
        </label>
        <label>
          &nbsp;
          <input
            type="time"
            value={value.end_time}
            onChange={(e) => set({ end_time: e.target.value })}
          />
        </label>
      </div>

      <h2>Permit?</h2>
      <label>
        Residential zone you hold (leave blank if none)
        <input
          type="text"
          inputMode="numeric"
          placeholder="e.g. 1439"
          value={value.permit_zone}
          onChange={(e) => set({ permit_zone: e.target.value })}
        />
      </label>

      <button className="primary" type="submit" disabled={!ready || busy}>
        {busy ? "Checking City data…" : "Check parking"}
      </button>
    </form>
  );
}
