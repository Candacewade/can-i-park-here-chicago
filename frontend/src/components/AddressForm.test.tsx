import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AddressInput, ExampleAddress } from "../types";
import { AddressForm } from "./AddressForm";

// AddressForm lazy-loads the real MapPicker (which pulls in maplibre-gl --
// no WebGL in jsdom). Stub it so these tests exercise AddressForm's own
// toggle/wiring, not the third-party map itself (that's MapPicker.test.tsx's job).
vi.mock("./MapPicker", () => ({
  MapPicker: ({ onPick }: { onPick: (lat: number, lon: number) => void }) => (
    <button onClick={() => onPick(41.9, -87.6)}>MOCK MAP</button>
  ),
}));

const value: AddressInput = { number: "", street: "", zip: "" };
const examples: ExampleAddress[] = [];

describe("AddressForm — use my current location", () => {
  it("hides the button when onLocateMe isn't provided", () => {
    render(
      <AddressForm value={value} onChange={vi.fn()} onSubmit={vi.fn()} examples={examples} busy={false} />,
    );
    expect(screen.queryByText(/Use my current location/)).toBeNull();
  });

  it("shows the button and calls onLocateMe when provided", () => {
    const onLocateMe = vi.fn();
    render(
      <AddressForm
        value={value}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        examples={examples}
        busy={false}
        onLocateMe={onLocateMe}
      />,
    );
    fireEvent.click(screen.getByText("Use my current location"));
    expect(onLocateMe).toHaveBeenCalled();
  });

  it("shows a locating state and disables the button while in progress", () => {
    render(
      <AddressForm
        value={value}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        examples={examples}
        busy={false}
        onLocateMe={vi.fn()}
        locating
      />,
    );
    const button = screen.getByRole("button", { name: /Finding your block/ }) as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.disabled).toBe(true);
  });

  it("states the coordinates are never stored", () => {
    render(
      <AddressForm
        value={value}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        examples={examples}
        busy={false}
        onLocateMe={vi.fn()}
      />,
    );
    expect(screen.getByText(/never stored/)).toBeTruthy();
  });
});

describe("AddressForm — pick on a map", () => {
  it("hides the button when onMapPick isn't provided", () => {
    render(
      <AddressForm value={value} onChange={vi.fn()} onSubmit={vi.fn()} examples={examples} busy={false} />,
    );
    expect(screen.queryByText(/Pick on a map/)).toBeNull();
  });

  it("opens the map on click and hides it again", async () => {
    render(
      <AddressForm
        value={value}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        examples={examples}
        busy={false}
        onMapPick={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Pick on a map"));
    expect(await screen.findByText("MOCK MAP")).toBeTruthy();
    expect(screen.getByText("Hide map")).toBeTruthy();

    fireEvent.click(screen.getByText("Hide map"));
    expect(screen.queryByText("MOCK MAP")).toBeNull();
  });

  it("picking a point on the map calls onMapPick and closes the map", async () => {
    const onMapPick = vi.fn();
    render(
      <AddressForm
        value={value}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        examples={examples}
        busy={false}
        onMapPick={onMapPick}
      />,
    );
    fireEvent.click(screen.getByText("Pick on a map"));
    fireEvent.click(await screen.findByText("MOCK MAP"));

    expect(onMapPick).toHaveBeenCalledWith(41.9, -87.6);
    expect(screen.queryByText("MOCK MAP")).toBeNull();
    expect(screen.getByText("Pick on a map")).toBeTruthy();
  });
});
