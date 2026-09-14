import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MapPicker } from "./MapPicker";

// jsdom has no WebGL, so the real maplibre-gl can't construct a Map. Mock the
// whole surface MapPicker.tsx touches and drive it like a real map would:
// record what's registered, let the test fire a synthetic "click".
// vi.mock factories are hoisted above everything else in the file, so the
// shared state they close over must go through vi.hoisted().
const { listeners, mapInstances, addProtocol, geolocateTrigger } = vi.hoisted(() => {
  return {
    listeners: {} as Record<string, (e: unknown) => void>,
    mapInstances: [] as { options: unknown; remove: ReturnType<typeof vi.fn> }[],
    addProtocol: vi.fn(),
    geolocateTrigger: vi.fn(),
  };
});

vi.mock("maplibre-gl", () => {
  class FakeMap {
    options: unknown;
    addControl = vi.fn();
    remove = vi.fn();
    on = vi.fn((event: string, cb: (e: unknown) => void) => {
      listeners[event] = cb;
    });
    off = vi.fn();
    constructor(options: unknown) {
      this.options = options;
      mapInstances.push(this);
    }
  }
  class FakeGeolocateControl {
    trigger = geolocateTrigger;
  }
  return {
    Map: FakeMap,
    NavigationControl: vi.fn(),
    GeolocateControl: FakeGeolocateControl,
    addProtocol: (...a: unknown[]) => addProtocol(...a),
  };
});
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("pmtiles", () => ({
  Protocol: class {
    tile = vi.fn();
  },
}));
vi.mock("@protomaps/basemaps", () => ({
  layers: vi.fn(() => []),
  namedFlavor: vi.fn(() => ({})),
}));

beforeEach(() => {
  mapInstances.length = 0;
  for (const k of Object.keys(listeners)) delete listeners[k];
  addProtocol.mockClear();
  geolocateTrigger.mockClear();
});

describe("MapPicker", () => {
  it("constructs a map bounded to Chicago, registering pmtiles:// at most once ever", () => {
    render(<MapPicker onPick={vi.fn()} />);
    render(<MapPicker onPick={vi.fn()} />); // a second mount must not re-register the protocol
    // Registration happens once per page load (module-level flag), so across
    // the whole test file this is called at most once total, however many
    // times MapPicker is mounted -- never more.
    expect(addProtocol.mock.calls.length).toBeLessThanOrEqual(1);
    for (const call of addProtocol.mock.calls) expect(call[0]).toBe("pmtiles");
    expect(mapInstances).toHaveLength(2);
    const opts = mapInstances[0].options as { maxBounds: number[] };
    expect(opts.maxBounds).toEqual([-87.955, 41.63, -87.5, 42.04]);
  });

  it("calls onPick with (lat, lon) when the map is clicked", () => {
    const onPick = vi.fn();
    render(<MapPicker onPick={onPick} />);
    listeners["click"]({ lngLat: { lat: 41.9, lng: -87.6 } });
    expect(onPick).toHaveBeenCalledWith(41.9, -87.6);
  });

  it("triggers geolocate once the map style loads", async () => {
    render(<MapPicker onPick={vi.fn()} />);
    listeners["load"]({});
    await waitFor(() => expect(geolocateTrigger).toHaveBeenCalled());
  });

  it("removes the map on unmount", () => {
    const { unmount } = render(<MapPicker onPick={vi.fn()} />);
    const map = mapInstances[0];
    unmount();
    expect(map.remove).toHaveBeenCalled();
  });
});
