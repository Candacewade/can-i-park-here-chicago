import type { ResolveResponse, WhenInput } from "../types";

interface Props {
  resolved: ResolveResponse;
  side: string;
  onSide: (side: string) => void;
  when: WhenInput;
  onWhen: (w: WhenInput) => void;
  onSubmit: () => void;
  onBack: () => void;
  busy: boolean;
}

const SIDE_LABEL: Record<string, string> = {
  north: "North", south: "South", east: "East", west: "West",
};

export function BlockConfirm({
  resolved, side, onSide, when, onWhen, onSubmit, onBack, busy,
}: Props) {
  const set = (patch: Partial<WhenInput>) => onWhen({ ...when, ...patch });
  const block = resolved.from_cross_street
    ? `${resolved.street_name}, between ${resolved.from_cross_street} and ${resolved.to_cross_street}`
    : resolved.street_name;

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy) onSubmit();
      }}
    >
      <button type="button" className="link" onClick={onBack}>
        ‹ different address
      </button>

      <h2>Confirm the block</h2>
      <p className="confirm-addr">{resolved.matched_address}</p>
      <p>{block}</p>
      {resolved.neighborhood && <p className="note">{resolved.neighborhood}</p>}

      <div className="field">
        <span>
          Which side of the street?
          {resolved.side_confidence === "low" && (
            <em className="warn"> — please check the signs; we're not certain</em>
          )}
        </span>
        <div className="segmented">
          {resolved.side_options.map((o) => (
            <button
              type="button"
              key={o.side}
              className={side === o.side ? "on" : ""}
              onClick={() => onSide(o.side)}
            >
              {SIDE_LABEL[o.side] ?? o.side}
              {o.side === resolved.suggested_side ? " ★" : ""}
            </button>
          ))}
        </div>
      </div>

      {resolved.notes.map((n, i) => (
        <p key={i} className="note">{n}</p>
      ))}

      <h2>When?</h2>
      <div className="row">
        <label>
          Start
          <input type="date" value={when.start_date} onChange={(e) => set({ start_date: e.target.value })} />
        </label>
        <label>
          &nbsp;
          <input type="time" value={when.start_time} onChange={(e) => set({ start_time: e.target.value })} />
        </label>
      </div>
      <div className="row">
        <label>
          End
          <input type="date" value={when.end_date} onChange={(e) => set({ end_date: e.target.value })} />
        </label>
        <label>
          &nbsp;
          <input type="time" value={when.end_time} onChange={(e) => set({ end_time: e.target.value })} />
        </label>
      </div>

      <h2>Permit?</h2>
      <label>
        Residential zone you hold (blank if none)
        <input
          inputMode="numeric"
          placeholder="e.g. 1439"
          value={when.permit_zone}
          onChange={(e) => set({ permit_zone: e.target.value })}
        />
      </label>

      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Checking City data…" : "Check parking"}
      </button>
    </form>
  );
}
