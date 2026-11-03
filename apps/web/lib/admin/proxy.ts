import { getTranslations } from "next-intl/server";
import { routing, type Locale } from "@/i18n/routing";
import { adminLogin } from "./auth";

const SERVER_API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function requestLocale(request: Request): Locale {
  const header = request.headers.get("accept-language")?.slice(0, 2).toLowerCase();
  return (routing.locales as readonly string[]).includes(header ?? "") ? (header as Locale) : routing.defaultLocale;
}

async function signedOut(locale: Locale): Promise<Response> {
  const t = await getTranslations({ locale, namespace: "admin.errors" });
  const body = { type: "about:blank", status: 401, code: "auth.admin_required", title: t("signedOutTitle"), detail: t("signedOutBody") };
  return Response.json(body, { status: 401, headers: { "Content-Type": "application/problem+json" } });
}

/**
 * Forward an admin-console call to the API with the admin token, after checking the Auth.js
 * session here on the server. The browser only ever talks to this app.
 */
export async function forwardToApi(request: Request, path: string, method: "GET" | "POST" | "DELETE") {
  const locale = requestLocale(request);
  const login = await adminLogin();
  if (!login) return signedOut(locale);
  const headers: Record<string, string> = {
    Authorization: `Bearer ${process.env.ADMIN_API_TOKEN}`,
    "X-Admin-Login": login,
    "Accept-Language": locale,
    Accept: "application/json",
  };
  if (method === "POST") headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${SERVER_API_URL}${path}`, {
      method,
      headers,
      body: method === "POST" ? await request.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    return new Response(null, { status: 502 });
  }
  const out = new Headers({ "Cache-Control": "no-store" });
  for (const name of ["content-type", "content-language"]) {
    const value = res.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(res.status === 204 ? null : await res.text(), { status: res.status, headers: out });
}
