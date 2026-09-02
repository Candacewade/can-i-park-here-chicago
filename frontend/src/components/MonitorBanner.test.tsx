import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtendWatchResponse, MonitorState } from "../types";
import { MonitorBanner } from "./MonitorBanner";

const extendWatch = vi.fn();
const stopWatch = vi.fn();
vi.mock("../api", () => ({
  extendWatch: (...a: unknown[]) => extendWatch(...a),
  stopWatch: (...a: unknown[]) => stopWatch(...a),
}));

const monitor: MonitorState = {
  watchId: "wch_1",
  token: "tok_1",
  email: "wade.candace1@gmail.com",
  locationSummary: "W Grant Pl … north side (Lincoln Park)",
  throughDisplay: "Wednesday, September 3, 2026 at 9:00 AM",
  endLocal: "2026-09-03T09:00",
};

const okResponse: ExtendWatchResponse = {
  watch_id: "wch_1",
  manage_token: "tok_1",
  end_time: "2026-09-06T12:00:00-05:00",
  end_time_local: "2026-09-06T12:00",
  through_display: "Sunday, September 6, 2026 at 12:00 PM",
  status: "LEGAL_UNTIL",
  start_time_display: "…",
  end_time_display: "…",
  move_by_display: "Thursday, September 10, 2026 at 9:00 AM",
  urgent_alert: false,
  summary: "Your extended stay changes your parking status — you'll need to move by Thursday…",
};

beforeEach(() => {
  extendWatch.mockReset();
  stopWatch.mockReset();
});

function setup(over: Partial<Parameters<typeof MonitorBanner>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <MonitorBanner
      monitor={monitor}
      onChange={onChange}
      onStartChanging={vi.fn()}
      {...over}
    />,
  );
  return { onChange };
}

describe("MonitorBanner", () => {
  it("shows the three management actions", () => {
    setup();
    expect(screen.getByRole("button", { name: "Change parking spot" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Extend parking time" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Stop monitoring/ })).toBeTruthy();
  });

  it("clicking Extend opens the panel with the current end prefilled", () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Extend parking time" }));
    expect(screen.getByText(/Current end:/)).toBeTruthy();
    const date = screen.getByLabelText("New end") as HTMLInputElement;
    expect(date.value).toBe("2026-09-03");
  });

  it("opens straight into the extend panel from an email link", () => {
    setup({ extendOnOpen: true });
    expect(screen.getByRole("button", { name: "Update parking time" })).toBeTruthy();
  });

  it("rejects an end that is not later, without calling the API", () => {
    const { onChange } = setup({ extendOnOpen: true });
    fireEvent.change(screen.getByLabelText("New end"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Update parking time" }));
    expect(screen.getByText(/must be later/)).toBeTruthy();
    expect(extendWatch).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("successful extend updates the monitor and shows the re-evaluated result", async () => {
    extendWatch.mockResolvedValue(okResponse);
    const { onChange } = setup({ extendOnOpen: true });

    fireEvent.change(screen.getByLabelText("New end"), { target: { value: "2026-09-06" } });
    fireEvent.change(screen.getByDisplayValue("09:00"), { target: { value: "12:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Update parking time" }));

    await waitFor(() => expect(extendWatch).toHaveBeenCalledWith("wch_1", "tok_1", "2026-09-06T12:00"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        watchId: "wch_1",
        endLocal: "2026-09-06T12:00",
        throughDisplay: "Sunday, September 6, 2026 at 12:00 PM",
      }),
    );
    expect(await screen.findByText(/Monitoring extended/)).toBeTruthy();
    expect(screen.getByText(/Thursday, September 10, 2026 at 9:00 AM/)).toBeTruthy();
  });

  it("API failure shows an error and does not mutate local monitor state", async () => {
    extendWatch.mockRejectedValue(new Error("500 boom"));
    const { onChange } = setup({ extendOnOpen: true });

    fireEvent.change(screen.getByLabelText("New end"), { target: { value: "2026-09-06" } });
    fireEvent.click(screen.getByRole("button", { name: "Update parking time" }));

    expect(await screen.findByText(/500 boom/)).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("Stop monitoring clears the watch", async () => {
    stopWatch.mockResolvedValue({});
    const { onChange } = setup();
    fireEvent.click(screen.getByRole("button", { name: /Stop monitoring/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
  });
});
