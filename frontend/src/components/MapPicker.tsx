import { layers, namedFlavor } from "@protomaps/basemaps";
import {
  addProtocol,
  GeolocateControl,
  Map as MaplibreMap,
  NavigationControl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";

interface Props {
  /** Called with the tapped point's (lat, lon) -- the same shape "Use my
   * current location" hands to reverse-geocoding. */
  onPick: (lat: number, lon: number) => void;
}

// The exact bbox frontend/public/chicago.pmtiles was extracted with
// (backend/docs/location-model.md documents the extract command).
const CHICAGO_BOUNDS: [number, number, number, number] = [-87.955, 41.63, -87.5, 42.04];
const CHICAGO_CENTER: [number, number] = [-87.675, 41.85];

const ATTRIBUTION =
  '© <a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> ' +
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';

let protocolRegistered = false;

/** Registers the pmtiles:// scheme with MapLibre exactly once per page --
 * safe to call from every mount. */
function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol({ metadata: true });
  addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

/** A fully self-hosted, $0 map: Chicago-only vector tiles extracted from the
 * open Protomaps basemap (frontend/public/chicago.pmtiles, ~64MB, built once
 * with the free `pmtiles` CLI against Protomaps' public daily OSM build --
 * no ongoing external tile service, no API key, no rate limit). Rendered
 * with MapLibre GL (open source, no account). Tapping anywhere hands that
 * point to the SAME reverse-geocode pipeline "Use my current location"
 * already uses -- this component only ever produces a candidate (lat, lon);
 * the usual block/side confirmation step still happens afterward. The blue
 * "you are here" dot is MapLibre's built-in GeolocateControl, backed by the
 * browser's own navigator.geolocation (same free API, nothing new). */
export function MapPicker({ onPick }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const onPickRef = useRef(onPick);
  const [err, setErr] = useState<string | null>(null);

  // Keep the click handler's callback current without re-creating the map
  // every time the parent passes a new onPick -- refs must be written in an
  // effect, never during render.
  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    if (!containerRef.current) return;
    ensurePmtilesProtocol();

    const tilesUrl = `pmtiles://${window.location.origin}/chicago.pmtiles`;
    let map: MaplibreMap;
    try {
      map = new MaplibreMap({
        container: containerRef.current,
        style: {
          version: 8,
          glyphs: "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
          sprite: "https://protomaps.github.io/basemaps-assets/sprites/v4/light",
          sources: {
            protomaps: { type: "vector", url: tilesUrl, attribution: ATTRIBUTION },
          },
          layers: layers("protomaps", namedFlavor("light"), { lang: "en" }),
        },
        center: CHICAGO_CENTER,
        zoom: 10.2,
        maxBounds: CHICAGO_BOUNDS,
        attributionControl: { compact: true },
      });
    } catch (e) {
      setErr(String((e as Error).message ?? e));
      return;
    }

    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    const geolocate = new GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
      showUserLocation: true,
    });
    map.addControl(geolocate, "top-right");
    map.on("load", () => {
      // Best-effort: prompts for location once loaded so the blue dot shows
      // up right away. A decline just leaves the map usable without it.
      try {
        geolocate.trigger();
      } catch {
        /* ignore */
      }
    });
    map.on("error", (e) => setErr(String(e.error?.message ?? "map failed to load")));

    const handleClick = (e: { lngLat: { lat: number; lng: number } }) => {
      onPickRef.current(e.lngLat.lat, e.lngLat.lng);
    };
    map.on("click", handleClick);

    return () => {
      map.off("click", handleClick);
      map.remove();
    };
  }, []);

  if (err) {
    return (
      <p className="mon-err" role="alert">
        Couldn't load the map: {err}
      </p>
    );
  }

  return (
    <div>
      <div
        ref={containerRef}
        className="map-picker"
        role="application"
        aria-label="Map: tap your block to select it"
      />
      <p className="note" style={{ marginTop: 8 }}>
        Tap your block on the map — or tap the locate button to find yourself first.
      </p>
    </div>
  );
}
