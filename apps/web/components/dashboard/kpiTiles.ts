import type { KpiTone } from "@/components/ui/KpiTile";
import type { DashboardKpi } from "@/lib/api-types";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

export type Tile = { id: string; label: string; value: string; note?: string; tone: KpiTone; title: string };

type T = (key: string, values?: Record<string, string | number>) => string;

/** "+6.8 %" for a rise; a fall already carries its minus sign. */
const signed = (text: string, value: number) => (value > 0 ? `+${text}` : text);

/** Dashboard KPI → tile texts in the UI language (numbers formatted for the locale). */
export function kpiTile(kpi: DashboardKpi, locale: string, t: T): Tile {
  const base = { id: kpi.kpi_id, label: kpi.name, title: kpi.definition };
  const v = kpi.value;
  if (v == null) return { ...base, value: "—", tone: "neutral" };
  const change = (c: number | null | undefined) =>
    c == null ? undefined : t("kpi.change", { value: signed(formatPercent(locale, c), c) });
  switch (kpi.kpi_id) {
    case "total_spend":
      return { ...base, value: formatCompact(locale, v, "CAD"), note: change(kpi.change), tone: kpi.change ? "positive" : "neutral" };
    case "contract_count":
      return { ...base, value: formatNumber(locale, v, 0), note: change(kpi.change), tone: "neutral" };
    case "avg_value":
      return {
        ...base,
        value: formatCompact(locale, v, "CAD"),
        note: kpi.median == null ? undefined : t("kpi.median", { value: formatCompact(locale, kpi.median) }),
        tone: "neutral",
      };
    case "direct_award_share": {
      const pts = kpi.change_points;
      const points = pts == null ? undefined : t("kpi.points", { value: signed(formatNumber(locale, Math.round(pts * 1000) / 10), pts) });
      return { ...base, value: formatPercent(locale, v, 0), note: points, tone: pts && pts > 0 ? "attention" : "neutral" };
    }
    case "hhi":
      return { ...base, value: formatNumber(locale, v, 3), note: kpi.level_label ?? undefined, tone: "neutral" };
    case "quality_score": {
      const improved = kpi.before != null && kpi.before !== v;
      return {
        ...base,
        value: formatNumber(locale, v, 0),
        note: improved ? t("kpi.was", { value: formatNumber(locale, kpi.before as number, 0) }) : undefined,
        tone: improved && v > (kpi.before as number) ? "positive" : "neutral",
      };
    }
    default:
      return { ...base, value: formatNumber(locale, v), tone: "neutral" };
  }
}
