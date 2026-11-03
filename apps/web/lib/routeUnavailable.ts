import type { Problem } from "./api-types";

export const ROUTE_UNAVAILABLE = "client.route_unavailable";

/**
 * A 404 for the route itself (not for a dataset or a recipe): the API that answered is an older
 * version without this endpoint, e.g. while production is still deploying. Without this, a
 * framework 404 with no problem body looked like a sleeping engine ("waking up"). The texts are
 * translated where the problem is shown (`common.apiError.routeTitle` / `routeBody`).
 */
export function isRouteMissing(status: number, body: unknown): boolean {
  if (status !== 404) return false;
  if (!body || typeof body !== "object" || !("code" in body)) return true;
  return (body as { code: unknown }).code === "request.not_found";
}

export function routeUnavailable(): Problem {
  return { type: "about:blank", status: 404, code: ROUTE_UNAVAILABLE, title: "" };
}
