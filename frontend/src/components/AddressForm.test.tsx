import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AddressInput, ExampleAddress } from "../types";
import { AddressForm } from "./AddressForm";

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
