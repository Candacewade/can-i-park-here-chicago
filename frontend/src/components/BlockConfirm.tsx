import type { ResolveResponse, WhenInput } from "../types";
import { Step } from "./Step";

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
  north: "North",
  south: "South",
  east: "East",
  west: "West",
};

export function BlockConfirm({
  resolved,
  side,
  onSide,
  when,
  onWhen,
  onSubmit,
  onBack,
  busy,
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
      <button type="button" className="back" onClick={onBack}>
        ‹ Use a different address
      </button>

      <p className="confirm-addr">{resolved.matched_address}</p>
      <p className="confirm-block">{block}</p>
      {resolved.neighborhood && <p className="confirm-hood">{resolved.neighborhood}</p>}

      <Step
        n={2}
        title="Which side of the street?"
        hint={
          resolved.side_confidence === "low" ? (
            <span className="warn-text">
              Please check the posted signs — we're not certain which side this is.
            </span>
          ) : undefined
        }
      >
        <div className="segmented" role="group" aria-label="Side of the street">
          {resolved.side_options.map((o) => (
            <button
              type="button"
              key={o.side}
              aria-pressed={side === o.side}
              className={side === o.side ? "on" : ""}
              onClick={() => onSide(o.side)}
            >
              {SIDE_LABEL[o.side] ?? o.side}
              {o.side === resolved.suggested_side ? " ★" : ""}
            </button>
          ))}
        </div>
        {resolved.notes.map((n, i) => (
          <p key={i} className="note" style={{ marginTop: 10 }}>
            {n}
          </p>
        ))}
      </Step>

      <Step n={3} title="When?">
        <div className="row">
          <label>
            Start date
            <input
              type="date"
              value={when.start_date}
              onChange={(e) => set({ start_date: e.target.value })}
            />
          </label>
          <label>
            Start time
            <input
              type="time"
              value={when.start_time}
              onChange={(e) => set({ start_time: e.target.value })}
            />
          </label>
        </div>
        <div className="row">
          <label>
            End date
            <input
              type="date"
              value={when.end_date}
              onChange={(e) => set({ end_date: e.target.value })}
            />
          </label>
          <label>
            End time
            <input
              type="time"
              value={when.end_time}
              onChange={(e) => set({ end_time: e.target.value })}
            />
          </label>
        </div>
      </Step>

      <Step
        n={4}
        title="Permit?"
        hint="Leave blank if you don't hold a residential zone permit."
      >
        <label>
          Residential zone number
          <input
            inputMode="numeric"
            placeholder="e.g. 143"
            value={when.permit_zone}
            onChange={(e) => set({ permit_zone: e.target.value })}
          />
        </label>
      </Step>

      <div className="section">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Checking City data…" : "Check parking"}
        </button>
      </div>
    </form>
  );
}
