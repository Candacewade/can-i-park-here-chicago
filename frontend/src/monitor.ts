/**
 * Active-watch persistence. No account, no server session — just this browser.
 *
 * Startup precedence (resolved in App.tsx):
 *   1. an explicit email link  ?manage=<id>&token=<token>  identifies the watch
 *      the user wants to manage right now — it is verified via GET /api/watches
 *      and, if active, replaces whatever is in localStorage.
 *   2. otherwise, restore the active watch from localStorage.
 * A malformed / invalid link never destroys a valid stored watch.
 */
import type { MonitorState, WatchView } from "./types";

const KEY = "ciph_monitor";

export type LinkStatus = "none" | "loading" | "resolved" | "invalid";

export function saveMonitor(m: MonitorState | null): void {
  try {
    if (m) localStorage.setItem(KEY, JSON.stringify(m));
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode / storage blocked — best effort */
  }
}

/** The active watch remembered on this browser (no deep-link fallback). */
export function loadStoredMonitor(): MonitorState | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const m = JSON.parse(raw) as MonitorState;
      if (m && m.watchId && m.token) return m;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** The watch the current URL explicitly asks to manage, if any. */
export function readManageLink(): { watchId: string; token: string } | null {
  try {
    const q = new URLSearchParams(window.location.search);
    const watchId = q.get("manage");
    const token = q.get("token");
    if (watchId && token) return { watchId, token };
  } catch {
    /* ignore */
  }
  return null;
}

/** True when we have a watch+token but not enough to render its card yet. */
export function needsHydration(m: MonitorState | null): boolean {
  return !!m && (!m.locationSummary || !m.throughDisplay);
}

/** Strip the capability params from the address bar once we've handled them. */
export function clearManageLinkFromUrl(): void {
  try {
    if (window.location.search) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  } catch {
    /* ignore */
  }
}

/**
 * Resolve which watch the app should manage at startup.
 *
 * Precedence: an explicit `?manage=&token=` email link wins over localStorage —
 * the user is telling us which watch they want. We verify it with its token
 * before adopting it, and a bad/expired link never clobbers a valid stored watch.
 */
export async function resolveStartupMonitor(
  getWatch: (watchId: string, token: string) => Promise<WatchView>,
): Promise<{ monitor: MonitorState | null; linkStatus: LinkStatus }> {
  const stored = loadStoredMonitor();
  const link = readManageLink();
  if (!link) return { monitor: stored, linkStatus: "none" };

  try {
    const w = await getWatch(link.watchId, link.token);
    clearManageLinkFromUrl();
    if (w.status === "active") {
      const m: MonitorState = {
        watchId: link.watchId,
        token: link.token,
        locationSummary: w.location_summary ?? undefined,
        throughDisplay: w.through_display ?? undefined,
      };
      saveMonitor(m); // Watch B replaces whatever was stored
      return { monitor: m, linkStatus: "none" };
    }
    // resolved / expired: show an inactive state, keep the stored watch as-is
    return { monitor: stored, linkStatus: "resolved" };
  } catch {
    clearManageLinkFromUrl();
    return { monitor: stored, linkStatus: "invalid" }; // stored watch preserved
  }
}
