import type {
  AddressInput,
  AnalyzeResponse,
  CreateWatchResponse,
  ExampleAddress,
  ExtendWatchResponse,
  ReplaceWatchResponse,
  ResolveResponse,
  WatchView,
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

/** Naive local datetime strings; the backend interprets them as America/Chicago. */
export function whenTimes(when: WhenInput) {
  return {
    start_time: `${when.start_date}T${when.start_time}:00`,
    end_time: `${when.end_date}T${when.end_time}:00`,
    permit_zone: when.permit_zone.trim() || null,
  };
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
  return fetch(`${BASE}/api/parking/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ location_id: locationId, ...whenTimes(when) }),
  }).then((r) => json<AnalyzeResponse>(r));
}

// --- email monitoring -------------------------------------------------

export function createWatch(input: {
  location_id: string;
  when: WhenInput;
  email: string;
}): Promise<CreateWatchResponse> {
  return fetch(`${BASE}/api/watches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      location_id: input.location_id,
      email: input.email.trim(),
      ...whenTimes(input.when),
    }),
  }).then((r) => json<CreateWatchResponse>(r));
}

export function getWatch(watchId: string, token: string): Promise<WatchView> {
  return fetch(
    `${BASE}/api/watches/${encodeURIComponent(watchId)}?token=${encodeURIComponent(token)}`,
  ).then((r) => json<WatchView>(r));
}

export function stopWatch(watchId: string, token: string): Promise<unknown> {
  return fetch(
    `${BASE}/api/watches/${encodeURIComponent(watchId)}?token=${encodeURIComponent(token)}`,
    { method: "DELETE" },
  ).then((r) => json<unknown>(r));
}

/** Push the end time later on the SAME watch. `endLocal` is "YYYY-MM-DDTHH:MM". */
export function extendWatch(
  watchId: string,
  token: string,
  endLocal: string,
): Promise<ExtendWatchResponse> {
  return fetch(`${BASE}/api/watches/${encodeURIComponent(watchId)}/extend`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token, end_time: `${endLocal}:00` }),
  }).then((r) => json<ExtendWatchResponse>(r));
}

export function replaceWatch(
  watchId: string,
  token: string,
  input: { location_id: string; when: WhenInput; email?: string },
): Promise<ReplaceWatchResponse> {
  return fetch(`${BASE}/api/watches/${encodeURIComponent(watchId)}/replace`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      token,
      location_id: input.location_id,
      email: input.email?.trim() || null,
      ...whenTimes(input.when),
    }),
  }).then((r) => json<ReplaceWatchResponse>(r));
}
