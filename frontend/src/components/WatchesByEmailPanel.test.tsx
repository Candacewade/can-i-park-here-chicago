import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtendWatchResponse, WatchListItem } from "../types";
import { WatchesByEmailPanel } from "./WatchesByEmailPanel";

const listWatchesByEmail = vi.fn();
const extendWatch = vi.fn();
const stopWatch = vi.fn();
vi.mock("../api", () => ({
  listWatchesByEmail: (...a: unknown[]) => listWatchesByEmail(...a),
  extendWatch: (...a: unknown[]) => extendWatch(...a),
  stopWatch: (...a: unknown[]) => stopWatch(...a),
}));

const watchA: WatchListItem = {
  watch_id: "wch_a",
  manage_token: "tok_a",
  location_id: "w-wrightwood-ave-3300-north",
  start_time: "2026-09-14T22:00:00-05:00",
  end_time: "2026-09-16T20:49:00-05:00",
  permit_zone: null,
  status: "active",
  created_at: "2026-09-14T15:00:00-05:00",
  last_decision: null,
  last_checked_at: null,
  notified_count: 0,
  location_summary: "W Wrightwood Ave … north side (Logan Square)",
  through_display: "Wednesday, September 16, 2026 at 8:49 PM",
  end_time_local: "2026-09-16T20:49",
};

const watchB: WatchListItem = { ...watchA, watch_id: "wch_b", manage_token: "tok_b" };

beforeEach(() => {
  listWatchesByEmail.mockReset();
  extendWatch.mockReset();
  stopWatch.mockReset();
});

describe("WatchesByEmailPanel", () => {
  it("shows a loading state, then the fetched watches", async () => {
    listWatchesByEmail.mockResolvedValue([watchA, watchB]);
    render(<WatchesByEmailPanel token="tok_xyz" />);
    expect(screen.getByText(/Loading your parking watches/)).toBeTruthy();

    await waitFor(() => expect(listWatchesByEmail).toHaveBeenCalledWith("tok_xyz"));
    expect(await screen.findAllByText(/Wrightwood/)).toHaveLength(2);
  });

  it("shows an empty state with no active watches", async () => {
    listWatchesByEmail.mockResolvedValue([]);
    render(<WatchesByEmailPanel token="tok_xyz" />);
    expect(await screen.findByText(/No active parking watches/)).toBeTruthy();
  });

  it("an invalid/expired token shows an error, not a crash", async () => {
    listWatchesByEmail.mockRejectedValue(new Error("401 invalid or expired link"));
    render(<WatchesByEmailPanel token="bad" />);
    expect(await screen.findByText(/isn't valid or has expired/)).toBeTruthy();
  });

  it("Stop monitoring removes just that watch from the list", async () => {
    listWatchesByEmail.mockResolvedValue([watchA, watchB]);
    stopWatch.mockResolvedValue({});
    render(<WatchesByEmailPanel token="tok_xyz" />);
    await screen.findAllByText(/Wrightwood/);

    fireEvent.click(screen.getAllByRole("button", { name: /Stop monitoring/ })[0]);
    await waitFor(() => expect(stopWatch).toHaveBeenCalledWith("wch_a", "tok_a"));
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /Stop monitoring/ })).toHaveLength(1),
    );
  });

  it("Extend on one row updates only that row", async () => {
    listWatchesByEmail.mockResolvedValue([watchA, watchB]);
    const extended: ExtendWatchResponse = {
      watch_id: "wch_a",
      manage_token: "tok_a",
      end_time: "2026-09-20T20:49:00-05:00",
      end_time_local: "2026-09-20T20:49",
      through_display: "Sunday, September 20, 2026 at 8:49 PM",
      status: "LEGAL",
      start_time_display: null,
      end_time_display: null,
      move_by_display: null,
      urgent_alert: false,
      summary: "still clear",
    };
    extendWatch.mockResolvedValue(extended);
    render(<WatchesByEmailPanel token="tok_xyz" />);
    await screen.findAllByText(/Wrightwood/);

    fireEvent.click(screen.getAllByRole("button", { name: "Extend parking time" })[0]);
    fireEvent.change(screen.getByLabelText("New end"), { target: { value: "2026-09-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Update parking time" }));

    await waitFor(() =>
      expect(extendWatch).toHaveBeenCalledWith("wch_a", "tok_a", "2026-09-20T20:49"),
    );
    expect(await screen.findByText(/Updated — now monitoring through/)).toBeTruthy();
    // row A moved; row B (never extended) is untouched
    expect(screen.getAllByText(/September 20, 2026 at 8:49 PM/)).toHaveLength(2); // meta + banner, row A only
    expect(screen.getAllByText(/September 16, 2026 at 8:49 PM/)).toHaveLength(1); // row B's unchanged Through line
  });

  it("each row's Change parking spot link carries its own watch_id + manage_token", async () => {
    listWatchesByEmail.mockResolvedValue([watchA, watchB]);
    render(<WatchesByEmailPanel token="tok_xyz" />);
    await screen.findAllByText(/Wrightwood/);

    const links = screen.getAllByRole("link", { name: "Change parking spot" });
    expect(links[0].getAttribute("href")).toBe("/?manage=wch_a&token=tok_a");
    expect(links[1].getAttribute("href")).toBe("/?manage=wch_b&token=tok_b");
  });
});
