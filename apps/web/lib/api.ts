import type { Problem } from "./api-types";

/** Base URL for browser calls (uploads, polling). */
export const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Base URL for server-side calls from Next.js (inside docker compose: http://api:8000). */
const SERVER_API_URL = process.env.API_URL ?? PUBLIC_API_URL;

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; kind: "unreachable" }
  | { ok: false; kind: "problem"; problem: Problem };

/**
 * GET from the API on the server, in the UI language (ADR-0007). Never throws: a sleeping
 * free-tier API ("unreachable") is a normal state the page renders as "Waking up the engine".
 */
export async function apiGet<T>(path: string, locale: string, timeoutMs = 20_000): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${SERVER_API_URL}${path}`, {
      headers: { "Accept-Language": locale, Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body = await res.json().catch(() => null);
    if (res.ok) return { ok: true, data: body as T };
    if (body && typeof body === "object" && "code" in body) {
      return { ok: false, kind: "problem", problem: body as Problem };
    }
    return { ok: false, kind: "unreachable" };
  } catch {
    return { ok: false, kind: "unreachable" };
  }
}
