import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearManageLinkFromUrl,
  loadStoredMonitor,
  needsHydration,
  readManageLink,
  resolveStartupMonitor,
  saveMonitor,
} from "./monitor";
import type { WatchView } from "./types";

const watchA = {
  watchId: "wch_A",
  token: "tokA-000000000000",
  email: "wade.candace1@gmail.com",
  locationSummary: "W Grant Pl … north side (Lincoln Park)",
  throughDisplay: "Wednesday, September 3, 2026 at 9:00 AM",
};

function view(over: Partial<WatchView>): WatchView {
  return {
    watch_id: "wch_B",
    location_id: "loc_b",
    start_time: "2026-09-02T18:00:00",
    end_time: "2026-09-05T09:00:00",
    permit_zone: null,
    status: "active",
    created_at: "2026-09-01T00:00:00",
    last_decision: null,
    last_checked_at: null,
    notified_count: 0,
    location_summary: "N Clark St … west side (Lincoln Park)",
    through_display: "Saturday, September 5, 2026 at 9:00 AM",
    ...over,
  };
}

beforeEach(() => {
  localStorage.clear();
  history.replaceState({}, "", "/");
});
afterEach(() => {
  localStorage.clear();
  history.replaceState({}, "", "/");
});

describe("stored monitor", () => {
  it("saves and restores (refresh / return to the site)", () => {
    saveMonitor(watchA);
    expect(loadStoredMonitor()).toEqual(watchA);
  });

  it("clearing removes it", () => {
    saveMonitor(watchA);
    saveMonitor(null);
    expect(loadStoredMonitor()).toBeNull();
  });

  it("ignores a malformed localStorage value", () => {
    localStorage.setItem("ciph_monitor", "{not json");
    expect(loadStoredMonitor()).toBeNull();
  });

  it("needsHydration", () => {
    expect(needsHydration(watchA)).toBe(false);
    expect(needsHydration({ watchId: "x", token: "y" })).toBe(true);
    expect(needsHydration(null)).toBe(false);
  });

  it("readManageLink / clearManageLinkFromUrl", () => {
    history.replaceState({}, "", "/?manage=wch_1&token=t1");
    expect(readManageLink()).toEqual({ watchId: "wch_1", token: "t1" });
    clearManageLinkFromUrl();
    expect(window.location.search).toBe("");
  });
});

describe("resolveStartupMonitor precedence", () => {
  it("no deep link -> restores the stored watch", async () => {
    saveMonitor(watchA);
    const getWatch = vi.fn();
    const r = await resolveStartupMonitor(getWatch);
    expect(getWatch).not.toHaveBeenCalled();
    expect(r).toEqual({ monitor: watchA, linkStatus: "none" });
  });

  it("valid active deep link for Watch B overrides stored Watch A", async () => {
    saveMonitor(watchA);
    history.replaceState({}, "", "/?manage=wch_B&token=tokB-111111111111");
    const getWatch = vi.fn(async () => view({ status: "active" }));

    const r = await resolveStartupMonitor(getWatch);

    expect(getWatch).toHaveBeenCalledWith("wch_B", "tokB-111111111111");
    expect(r.linkStatus).toBe("none");
    expect(r.monitor?.watchId).toBe("wch_B");
    expect(r.monitor?.locationSummary).toBe("N Clark St … west side (Lincoln Park)");
    // persisted locally after hydration
    expect(loadStoredMonitor()?.watchId).toBe("wch_B");
    // capability params stripped from the URL
    expect(window.location.search).toBe("");
  });

  it("valid active deep link with nothing stored -> adopts it", async () => {
    history.replaceState({}, "", "/?manage=wch_B&token=tokB");
    const r = await resolveStartupMonitor(vi.fn(async () => view({ status: "active" })));
    expect(r.monitor?.watchId).toBe("wch_B");
    expect(loadStoredMonitor()?.watchId).toBe("wch_B");
  });

  it("invalid deep link does NOT erase stored Watch A", async () => {
    saveMonitor(watchA);
    history.replaceState({}, "", "/?manage=wch_B&token=bad");
    const getWatch = vi.fn(async () => {
      throw new Error("404 Not Found");
    });

    const r = await resolveStartupMonitor(getWatch);

    expect(r.linkStatus).toBe("invalid");
    expect(r.monitor).toEqual(watchA); // stored watch preserved
    expect(loadStoredMonitor()).toEqual(watchA); // localStorage untouched
  });

  it("resolved deep-link watch does not become the active local monitor", async () => {
    saveMonitor(watchA);
    history.replaceState({}, "", "/?manage=wch_B&token=tokB");
    const getWatch = vi.fn(async () => view({ status: "resolved" }));

    const r = await resolveStartupMonitor(getWatch);

    expect(r.linkStatus).toBe("resolved");
    expect(r.monitor).toEqual(watchA); // Watch A stays active
    expect(loadStoredMonitor()).toEqual(watchA); // not overwritten with Watch B
  });

  it("resolved deep-link watch with nothing stored -> no monitor", async () => {
    history.replaceState({}, "", "/?manage=wch_B&token=tokB");
    const r = await resolveStartupMonitor(vi.fn(async () => view({ status: "resolved" })));
    expect(r).toEqual({ monitor: null, linkStatus: "resolved" });
    expect(loadStoredMonitor()).toBeNull();
  });
});
