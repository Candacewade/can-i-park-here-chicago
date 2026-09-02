import { afterEach, describe, expect, it, vi } from "vitest";
import { createWatch, getWatch, replaceWatch, stopWatch } from "./api";
import type { WhenInput } from "./types";

const when: WhenInput = {
  start_date: "2026-09-02",
  start_time: "18:00",
  end_date: "2026-09-05",
  end_time: "09:00",
  permit_zone: "",
};

function mockFetch(status: number, body: unknown) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  })) as unknown as typeof fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("watch api", () => {
  it("createWatch posts the selected location + window + email", async () => {
    const f = mockFetch(201, {
      watch_id: "wch_1",
      manage_token: "tok_1",
      email_registered: true,
      note: "ok",
    });
    vi.stubGlobal("fetch", f);

    const r = await createWatch({ location_id: "n-clark-st-2400-west", when, email: "a@b.com" });
    expect(r.watch_id).toBe("wch_1");

    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/watches$/);
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent).toMatchObject({
      location_id: "n-clark-st-2400-west",
      email: "a@b.com",
      start_time: "2026-09-02T18:00:00",
      end_time: "2026-09-05T09:00:00",
    });
  });

  it("createWatch surfaces a server error (e.g. bad email -> 422)", async () => {
    vi.stubGlobal("fetch", mockFetch(422, { detail: "not a valid email address" }));
    await expect(
      createWatch({ location_id: "x", when, email: "nope" }),
    ).rejects.toThrow(/not a valid email/);
  });

  it("getWatch passes the capability token (email link on a fresh device)", async () => {
    const f = mockFetch(200, { status: "active", location_summary: "S", through_display: "T" });
    vi.stubGlobal("fetch", f);
    const w = await getWatch("wch_9", "secret-token");
    expect(w.location_summary).toBe("S");
    const [url] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).toContain("/api/watches/wch_9?token=secret-token");
  });

  it("stopWatch calls DELETE with the token", async () => {
    const f = mockFetch(200, {});
    vi.stubGlobal("fetch", f);
    await stopWatch("wch_9", "t");
    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init as RequestInit).method).toBe("DELETE");
    expect(String(url)).toContain("/api/watches/wch_9?token=t");
  });

  it("replaceWatch posts token + new location; omitted email -> null (reuse)", async () => {
    const f = mockFetch(200, {
      old_watch_id: "wch_old",
      watch_id: "wch_new",
      manage_token: "tok_new",
      email_registered: true,
    });
    vi.stubGlobal("fetch", f);

    const r = await replaceWatch("wch_old", "tok_old", { location_id: "loc_new", when });
    expect(r.watch_id).toBe("wch_new");
    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).toContain("/api/watches/wch_old/replace");
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent).toMatchObject({ token: "tok_old", location_id: "loc_new", email: null });
  });
});
