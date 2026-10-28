import type { Locale } from "@/i18n/routing";

/**
 * UI locale → Intl locale. Formatting follows the UI language, never the data language
 * (en → 1,234.56 · es → 1.234,56). See ROADMAP Phase 3 "Locale formatting".
 */
export const INTL_LOCALE: Record<Locale, string> = { en: "en-CA", es: "es-CO" };

const intl = (locale: string) => INTL_LOCALE[locale as Locale] ?? INTL_LOCALE.en;

export function formatNumber(locale: string, value: number, digits?: number): string {
  return new Intl.NumberFormat(intl(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits ?? 2,
  }).format(value);
}

/** Currency with its ISO code always visible (e.g. "CAD 1,234.56", "COP 1.234,56"). */
export function formatCurrency(locale: string, value: number, currency: string, digits = 2): string {
  const number = formatNumber(locale, value, digits);
  return `${currency} ${number}`;
}

/** Compact amount, e.g. 412.6M / 412,6 M. Currency code kept. */
export function formatCompact(locale: string, value: number, currency?: string): string {
  const number = new Intl.NumberFormat(intl(locale), {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
  return currency ? `${currency} ${number}` : number;
}

export function formatPercent(locale: string, ratio: number, digits = 1): string {
  return new Intl.NumberFormat(intl(locale), {
    style: "percent",
    maximumFractionDigits: digits,
  }).format(ratio);
}

export function formatDate(
  locale: string,
  value: Date | string,
  style: "short" | "long" = "long",
): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat(intl(locale), { dateStyle: style, timeZone: "UTC" }).format(date);
}
