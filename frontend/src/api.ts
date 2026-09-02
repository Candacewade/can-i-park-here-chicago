import type {
  AddressInput,
  AnalyzeResponse,
  ExampleAddress,
  ResolveResponse,
  WhenInput,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail)
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchExamples(): Promise<ExampleAddress[]> {
  return fetch(`${BASE}/api/locations/examples`).then((r) => json<ExampleAddress[]>(r));
}

export function resolveAddress(addr: AddressInput, side?: string): Promise<ResolveResponse> {
  return fetch(`${BASE}/api/locations/resolve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      number: Number(addr.number),
      street: addr.street.trim(),
      zip_code: addr.zip.trim(),
      side: side ?? null,
    }),
  }).then((r) => json<ResolveResponse>(r));
}

export function analyze(locationId: string, when: WhenInput): Promise<AnalyzeResponse> {
  const payload = {
    location_id: locationId,
    start_time: `${when.start_date}T${when.start_time}:00`,
    end_time: `${when.end_date}T${when.end_time}:00`,
    permit_zone: when.permit_zone.trim() || null,
  };
  return fetch(`${BASE}/api/parking/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then((r) => json<AnalyzeResponse>(r));
}
