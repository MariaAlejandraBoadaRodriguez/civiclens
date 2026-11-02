import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import en from "@/messages/en.json";
import es from "@/messages/es.json";

export function renderIn(locale: "en" | "es", ui: ReactElement) {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === "en" ? en : es} timeZone="UTC">
      {ui}
    </NextIntlClientProvider>,
  );
}

/** A Response like Render's 502 page while the instance restarts: HTML, no CORS, no JSON. */
export const badGateway = () =>
  new Response("<html><body>502 Bad Gateway</body></html>", { status: 502, headers: { "Content-Type": "text/html" } });

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
