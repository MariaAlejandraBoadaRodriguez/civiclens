import { PUBLIC_API_URL } from "./api";
import type { Job, Problem } from "./api-types";

/**
 * Browser calls to the API. Every failure comes back as a value the UI must show — never a
 * thrown error that a component could swallow:
 * - `problem`: the API answered with an RFC 7807 problem (already localized);
 * - `unavailable`: no usable answer — network error, a 5xx (e.g. Render's 502 while the
 *   instance restarts, which carries no CORS headers, so the browser reports it as a network
 *   error), or a body that is not JSON.
 */
export type ApiFailure =
  | { kind: "problem"; problem: Problem }
  | { kind: "unavailable"; status?: number };

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiFailure };

type Options = {
  locale: string;
  method?: "GET" | "POST";
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
};

export async function apiRequest<T>(path: string, options: Options): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { "Accept-Language": options.locale, Accept: "application/json" };
  if (options.json !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${PUBLIC_API_URL}${path}`, {
      method: options.method ?? (options.json !== undefined || options.form ? "POST" : "GET"),
      headers,
      body: options.form ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error; // the caller cancelled: not a failure to show
    return { ok: false, error: { kind: "unavailable" } };
  }
  const body: unknown = await res.json().catch(() => null);
  if (res.ok && body !== null) return { ok: true, data: body as T };
  if (res.status < 500 && body && typeof body === "object" && "code" in body) {
    return { ok: false, error: { kind: "problem", problem: body as Problem } };
  }
  return { ok: false, error: { kind: "unavailable", status: res.status } };
}

/** Poll a job until it succeeds or fails; a failed job becomes a `problem`. */
export async function waitForJob(
  jobId: string,
  locale: string,
  { intervalMs = 1000, maxTries = 300 }: { intervalMs?: number; maxTries?: number } = {},
): Promise<ApiResult<Job>> {
  for (let n = 0; n < maxTries; n += 1) {
    const res = await apiRequest<Job>(`/api/v1/jobs/${jobId}`, { locale });
    if (!res.ok) return res;
    if (res.data.status === "succeeded") return res;
    if (res.data.status === "failed") {
      return res.data.error
        ? { ok: false, error: { kind: "problem", problem: res.data.error } }
        : { ok: false, error: { kind: "unavailable" } };
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return { ok: false, error: { kind: "unavailable" } };
}
