import type { AnalyzeResponse, LocationsResponse, ParkingSelection } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchLocations(): Promise<LocationsResponse> {
  return fetch(`${BASE}/api/locations`).then((r) => json<LocationsResponse>(r));
}

export function analyze(sel: ParkingSelection): Promise<AnalyzeResponse> {
  const payload = {
    location_id: sel.location_id,
    start_time: `${sel.start_date}T${sel.start_time}:00`,
    end_time: `${sel.end_date}T${sel.end_time}:00`,
    permit_zone: sel.permit_zone.trim() || null,
  };
  return fetch(`${BASE}/api/parking/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then((r) => json<AnalyzeResponse>(r));
}
