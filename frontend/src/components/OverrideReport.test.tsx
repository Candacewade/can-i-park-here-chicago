import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { WatchOverrideView } from "../types";
import { OverrideReport } from "./OverrideReport";

const setWatchOverride = vi.fn();
const clearWatchOverride = vi.fn();
vi.mock("../api", () => ({
  setWatchOverride: (...a: unknown[]) => setWatchOverride(...a),
  clearWatchOverride: (...a: unknown[]) => clearWatchOverride(...a),
}));

const override: WatchOverrideView = {
  status: "NOT_LEGAL",
  move_by: null,
  move_by_display: null,
  note: "Orange street cleaning sign, Thu 9am-2pm",
  reported_at: "2026-09-14T10:00:00-05:00",
  expires_at: "2026-09-15T10:00:00-05:00",
  expires_at_local: "2026-09-15T10:00",
};

beforeEach(() => {
  setWatchOverride.mockReset();
  clearWatchOverride.mockReset();
});

function setup(over: Partial<Parameters<typeof OverrideReport>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <OverrideReport
      watchId="wch_1"
      manageToken="tok_1"
      override={null}
      onChange={onChange}
      {...over}
    />,
  );
  return { onChange };
}

describe("OverrideReport", () => {
  it("starts as a single link when no override is active", () => {
    setup();
    expect(screen.getByText(/Report what you see/)).toBeTruthy();
  });

  it("shows the active override with source clearly labeled", () => {
    setup({ override });
    expect(screen.getByText(/You reported this/)).toBeTruthy();
    expect(screen.getByText(/not verified city data/)).toBeTruthy();
    expect(screen.getByText('"Orange street cleaning sign, Thu 9am-2pm"')).toBeTruthy();
  });

  it("requires a note and an expiry before submitting", () => {
    setup();
    fireEvent.click(screen.getByText(/Report what you see/));
    fireEvent.click(screen.getByRole("button", { name: "Save my report" }));
    expect(screen.getByText(/Say what you saw/)).toBeTruthy();
    expect(setWatchOverride).not.toHaveBeenCalled();
  });

  it("LEGAL_UNTIL requires a move-by time", () => {
    setup();
    fireEvent.click(screen.getByText(/Report what you see/));
    fireEvent.change(screen.getByLabelText(/What's actually true here/), {
      target: { value: "LEGAL_UNTIL" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Orange street cleaning sign/), {
      target: { value: "Sign says cleaning starts at 9am" },
    });
    fireEvent.change(screen.getByLabelText("Applies until"), {
      target: { value: "2026-09-15T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save my report" }));
    expect(screen.getByText(/Pick the time you need to move by/)).toBeTruthy();
    expect(setWatchOverride).not.toHaveBeenCalled();
  });

  it("submits a valid report and hands the new override back", async () => {
    setWatchOverride.mockResolvedValue({ override });
    const { onChange } = setup();
    fireEvent.click(screen.getByText(/Report what you see/));
    fireEvent.change(screen.getByPlaceholderText(/Orange street cleaning sign/), {
      target: { value: "Orange street cleaning sign, Thu 9am-2pm" },
    });
    fireEvent.change(screen.getByLabelText("Applies until"), {
      target: { value: "2026-09-15T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save my report" }));

    await waitFor(() =>
      expect(setWatchOverride).toHaveBeenCalledWith("wch_1", "tok_1", {
        status: "NOT_LEGAL",
        note: "Orange street cleaning sign, Thu 9am-2pm",
        expiresAtLocal: "2026-09-15T10:00",
        moveByLocal: undefined,
      }),
    );
    expect(onChange).toHaveBeenCalledWith(override);
  });

  it("clearing calls the API and hands back null", async () => {
    clearWatchOverride.mockResolvedValue({ override: null });
    const { onChange } = setup({ override });
    fireEvent.click(screen.getByText("Clear my report"));
    await waitFor(() => expect(clearWatchOverride).toHaveBeenCalledWith("wch_1", "tok_1"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("API failure on submit shows an error and keeps the form open", async () => {
    setWatchOverride.mockRejectedValue(new Error("500 boom"));
    setup();
    fireEvent.click(screen.getByText(/Report what you see/));
    fireEvent.change(screen.getByPlaceholderText(/Orange street cleaning sign/), {
      target: { value: "Sign" },
    });
    fireEvent.change(screen.getByLabelText("Applies until"), {
      target: { value: "2026-09-15T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save my report" }));
    expect(await screen.findByText(/500 boom/)).toBeTruthy();
  });
});
