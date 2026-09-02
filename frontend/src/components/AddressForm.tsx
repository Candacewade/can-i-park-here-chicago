import type { AddressInput, ExampleAddress } from "../types";

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
      <h2>Where are you parking?</h2>
      <p className="hint">Enter the exact Chicago address you're parked at (or next to).</p>

      <div className="row">
        <label style={{ flex: "0 0 90px" }}>
          Number
          <input
            inputMode="numeric"
            placeholder="2400"
            value={value.number}
            onChange={(e) => set({ number: e.target.value.replace(/[^0-9]/g, "") })}
          />
        </label>
        <label style={{ flex: 1 }}>
          Street
          <input
            placeholder="N Clark St"
            value={value.street}
            onChange={(e) => set({ street: e.target.value })}
          />
        </label>
        <label style={{ flex: "0 0 90px" }}>
          ZIP
          <input
            inputMode="numeric"
            placeholder="60614"
            value={value.zip}
            onChange={(e) => set({ zip: e.target.value.replace(/[^0-9]/g, "").slice(0, 5) })}
          />
        </label>
      </div>

      <button className="primary" type="submit" disabled={!ready || busy}>
        {busy ? "Looking up the block…" : "Find my block"}
      </button>

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
    </form>
  );
}
