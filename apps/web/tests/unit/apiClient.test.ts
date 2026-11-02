import { describe, expect, it, vi } from "vitest";
import { apiRequest, waitForJob } from "@/lib/apiClient";
import { badGateway, json } from "./render";

describe("apiRequest", () => {
  it("turns Render's 502 page (HTML, no CORS) into 'unavailable', never a throw", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(badGateway()));
    await expect(apiRequest("/api/v1/recipes/preview", { locale: "en", json: {} })).resolves.toEqual({
      ok: false,
      error: { kind: "unavailable", status: 502 },
    });
  });

  it("turns a network/CORS error into 'unavailable'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const res = await apiRequest("/api/v1/query", { locale: "es", json: {} });
    expect(res).toEqual({ ok: false, error: { kind: "unavailable" } });
  });

  it("keeps the API's localized problem for 4xx answers", async () => {
    const problem = { type: "x", title: "Solo se permiten consultas de lectura", status: 400, code: "sql.forbidden_statement" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(problem, 400)));
    const res = await apiRequest("/api/v1/query", { locale: "es", json: {} });
    expect(res).toEqual({ ok: false, error: { kind: "problem", problem } });
  });

  it("sends the UI language and returns the data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ items: [1] }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/api/v1/guided-queries", { locale: "es" })).resolves.toEqual({ ok: true, data: { items: [1] } });
    expect(fetchMock.mock.calls[0][1].headers["Accept-Language"]).toBe("es");
  });

  it("lets a cancelled request throw (the caller ignores it)", async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    await expect(apiRequest("/x", { locale: "en", signal: controller.signal })).rejects.toThrow();
  });
});

describe("waitForJob", () => {
  it("returns the job's localized problem when it failed", async () => {
    const error = { type: "x", title: "The job ran out of memory", status: 422, code: "job.out_of_memory" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ id: "j", status: "failed", error })));
    await expect(waitForJob("j", "en", { intervalMs: 1 })).resolves.toEqual({ ok: false, error: { kind: "problem", problem: error } });
  });

  it("reports 'unavailable' when the engine stops answering while polling", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(json({ id: "j", status: "running" })).mockResolvedValue(badGateway()),
    );
    const res = await waitForJob("j", "en", { intervalMs: 1 });
    expect(res).toEqual({ ok: false, error: { kind: "unavailable", status: 502 } });
  });
});
