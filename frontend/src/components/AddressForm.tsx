import type { AddressInput, ExampleAddress } from "../types";
import { Icon } from "./Icon";
import { Step } from "./Step";

interface Props {
  value: AddressInput;
  onChange: (a: AddressInput) => void;
  onSubmit: () => void;
  examples: ExampleAddress[];
  busy: boolean;
}

export function AddressForm({ value, onChange, onSubmit, examples, busy }: Props) {
  const set = (patch: Partial<AddressInput>) => onChange({ ...value, ...patch });
  const ready = value.number.trim() && value.street.trim();

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) onSubmit();
      }}
    >
      <Step
        n={1}
        title="Where are you parking?"
        hint="The exact Chicago address you're parked at, or next to."
      >
        <div className="row">
          <label className="narrow">
            Number
            <input
              inputMode="numeric"
              autoComplete="off"
              placeholder="2400"
              value={value.number}
              onChange={(e) => set({ number: e.target.value.replace(/[^0-9]/g, "") })}
            />
          </label>
          <label>
            Street
            <input
              placeholder="N Clark St"
              autoComplete="off"
              value={value.street}
              onChange={(e) => set({ street: e.target.value })}
            />
          </label>
        </div>
        <label>
          ZIP code <span className="opt">(optional)</span>
          <input
            inputMode="numeric"
            autoComplete="postal-code"
            placeholder="60614"
            value={value.zip}
            onChange={(e) => set({ zip: e.target.value.replace(/[^0-9]/g, "").slice(0, 5) })}
          />
        </label>

        <button className="primary" type="submit" disabled={!ready || busy}>
          <Icon name="search" size={18} />
          {busy ? "Looking up the block…" : "Find my block"}
        </button>

        <p className="privacy-note">
          <Icon name="shield" size={14} /> We never store your location — one-time lookups
          only.
        </p>

        {examples.length > 0 && (
          <p className="examples">
            Try:{" "}
            {examples.map((ex, i) => (
              <span key={i}>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    onChange({ number: String(ex.number), street: ex.street, zip: ex.zip_code })
                  }
                >
                  {ex.number} {ex.street}
                </button>
                {i < examples.length - 1 ? " · " : ""}
              </span>
            ))}
          </p>
        )}
      </Step>
    </form>
  );
}
