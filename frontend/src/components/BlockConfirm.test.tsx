import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ResolveResponse, WhenInput } from "../types";
import { BlockConfirm } from "./BlockConfirm";

function resolved(overrides: Partial<ResolveResponse> = {}): ResolveResponse {
  return {
    in_chicago: true,
    matched_address: "3300 W WRIGHTWOOD AVE, CHICAGO, IL, 60647",
    street_name: "W Wrightwood Ave",
    neighborhood: "Logan Square",
    from_cross_street: "N Spaulding Ave",
    to_cross_street: "N Kimball Ave",
    street_sweeping_ward: "35",
    street_sweeping_section: "09",
    latitude: 41.93,
    longitude: -87.71,
    suggested_side: "north",
    side_confidence: "high",
    side_options: [
      {
        side: "north",
        location_id: "w-wrightwood-ave-3300-north",
        summary: "north side",
        required_permit_zone: "143",
        permit_zone_is_buffer: false,
      },
      {
        side: "south",
        location_id: "w-wrightwood-ave-3300-south",
        summary: "south side",
        required_permit_zone: null,
        permit_zone_is_buffer: false,
      },
    ],
    notes: [],
    ...overrides,
  };
}

function defaultWhen(over: Partial<WhenInput> = {}): WhenInput {
  return {
    start_date: "2026-09-14",
    start_time: "19:00",
    end_date: "2026-09-15",
    end_time: "09:00",
    permit_zone: "",
    ...over,
  };
}

function Harness({
  r,
  side: initialSide,
  when: initialWhen,
}: {
  r: ResolveResponse;
  side: string;
  when: WhenInput;
}) {
  const [side, setSide] = useState(initialSide);
  const [when, setWhen] = useState(initialWhen);
  return (
    <BlockConfirm
      resolved={r}
      side={side}
      onSide={setSide}
      when={when}
      onWhen={setWhen}
      onSubmit={vi.fn()}
      onBack={vi.fn()}
      busy={false}
    />
  );
}

describe("BlockConfirm permit-zone suggestion", () => {
  it("auto-fills the required zone when the field starts empty", () => {
    render(<Harness r={resolved()} side="north" when={defaultWhen()} />);
    const input = screen.getByLabelText("Residential zone number") as HTMLInputElement;
    expect(input.value).toBe("143");
    expect(screen.getByText(/This block requires/)).toBeTruthy();
  });

  it("never overwrites an already-entered/remembered value", () => {
    render(<Harness r={resolved()} side="north" when={defaultWhen({ permit_zone: "77" })} />);
    const input = screen.getByLabelText("Residential zone number") as HTMLInputElement;
    expect(input.value).toBe("77");
    // and flags the mismatch rather than silently overwriting it
    expect(screen.getByText(/you've entered Zone 77/)).toBeTruthy();
  });

  it('clicking "Use Zone X" accepts the suggestion over a mismatched value', () => {
    render(<Harness r={resolved()} side="north" when={defaultWhen({ permit_zone: "77" })} />);
    fireEvent.click(screen.getByRole("button", { name: "Use Zone 143" }));
    const input = screen.getByLabelText("Residential zone number") as HTMLInputElement;
    expect(input.value).toBe("143");
  });

  it("says no permit is required when the side has no zone", () => {
    render(<Harness r={resolved()} side="south" when={defaultWhen()} />);
    expect(screen.getByText(/No residential permit is required/)).toBeTruthy();
    const input = screen.getByLabelText("Residential zone number") as HTMLInputElement;
    expect(input.value).toBe(""); // nothing to suggest -> nothing filled
  });

  it("flags a buffer zone distinctly", () => {
    const r = resolved({
      side_options: [
        {
          side: "north",
          location_id: "loc-north",
          summary: "north side",
          required_permit_zone: "100",
          permit_zone_is_buffer: true,
        },
      ],
    });
    render(<Harness r={r} side="north" when={defaultWhen()} />);
    expect(screen.getByText(/buffer zone/)).toBeTruthy();
  });
});
