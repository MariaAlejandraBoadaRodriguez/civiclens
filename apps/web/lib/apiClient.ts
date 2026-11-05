import { PUBLIC_API_URL } from "./api";
import type { Job, Problem } from "./api-types";
import { isRouteMissing, routeUnavailable } from "./routeUnavailable";

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
  method?: "GET" | "POST" | "DELETE";
  /** Base URL; "" calls this web app's own route handlers (e.g. the admin console's). */
  base?: string;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
};

export async function apiRequest<T>(path: string, options: Options): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { "Accept-Language": options.locale, Accept: "application/json" };
  if (options.json !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${options.base ?? PUBLIC_API_URL}${path}`, {
      method: options.method ?? (options.json !== undefined || options.form ? "POST" : "GET"),
      headers,
      body: options.form ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error; // the caller cancelled: not a failure to show
    return { ok: false, error: { kind: "unavailable" } };
  }
  if (res.status === 204) return { ok: true, data: null as T };
  const body: unknown = await res.json().catch(() => null);
  if (res.ok && body !== null) return { ok: true, data: body as T };
  if (isRouteMissing(res.status, body)) {
    return { ok: false, error: { kind: "problem", problem: routeUnavailable() } };
  }
  if (res.status < 500 && body && typeof body === "object" && "code" in body) {
    return { ok: false, error: { kind: "problem", problem: body as Problem } };
  }
  return { ok: false, error: { kind: "unavailable", status: res.status } };
}

/** Poll a job until it succeeds or fails; a failed job becomes a `problem`. `onProgress`
 * receives every poll (phase, localized label, percent) for the progress bar. */
export async function waitForJob(
  jobId: string,
  locale: string,
  {
    intervalMs = 1000,
    maxTries = 300,
    onProgress,
  }: { intervalMs?: number; maxTries?: number; onProgress?: (job: Job) => void } = {},
): Promise<ApiResult<Job>> {
  for (let n = 0; n < maxTries; n += 1) {
    const res = await apiRequest<Job>(`/api/v1/jobs/${jobId}`, { locale });
    if (!res.ok) return res;
    onProgress?.(res.data);
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

/**
 * Upload a form with the browser's upload progress (fetch cannot report it). Same result shape
 * and failure rules as `apiRequest`; `onProgress` gets 0–100 while the bytes are sent.
 */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  locale: string,
  onProgress: (percent: number) => void,
): Promise<ApiResult<T>> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${PUBLIC_API_URL}${path}`);
    xhr.setRequestHeader("Accept-Language", locale);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)));
    };
    xhr.onerror = () => resolve({ ok: false, error: { kind: "unavailable" } });
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && body !== null) {
        onProgress(100);
        resolve({ ok: true, data: body as T });
      } else if (xhr.status < 500 && body && typeof body === "object" && "code" in body) {
        resolve({ ok: false, error: { kind: "problem", problem: body as Problem } });
      } else {
        resolve({ ok: false, error: { kind: "unavailable", status: xhr.status } });
      }
    };
    xhr.send(form);
  });
}
