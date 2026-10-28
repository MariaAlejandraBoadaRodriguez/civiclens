import type { KpiValue, PreviewCell } from "@/lib/api-types";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

/** Preview cell → display text. Text stays as written (data); numbers use the UI locale. */
export function cellText(cell: PreviewCell, locale: string, empty: string): string {
  if (cell === null) return empty;
  if (typeof cell === "number") return formatNumber(locale, cell, Number.isInteger(cell) ? 0 : 2);
  if (typeof cell === "boolean") return String(cell);
  return cell;
}

export function kpiText(kpi: KpiValue | null | undefined, locale: string, fallback: string): string {
  if (!kpi || kpi.value === null || kpi.value === undefined) return fallback;
  if (kpi.unit === "ratio") return formatPercent(locale, kpi.value, 1);
  if (kpi.currency) return formatCompact(locale, kpi.value, kpi.currency);
  return formatNumber(locale, kpi.value);
}
