import { useLocale, useTranslations } from "next-intl";
import type { Kpi } from "@/lib/api-types";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

function value(locale: string, kpi: Kpi): string {
  if (kpi.value === null) return "—";
  switch (kpi.unit) {
    case "currency":
      return formatCompact(locale, kpi.value, kpi.currency ?? undefined);
    case "ratio":
      return formatPercent(locale, kpi.value);
    case "index":
      return formatNumber(locale, kpi.value, 3);
    default:
      return formatNumber(locale, kpi.value, 0);
  }
}

/** KPI catalog: one definition per KPI (name + definition localized, SQL shared). */
export function KpiCatalog({ items }: { items: Kpi[] }) {
  const t = useTranslations("sql.kpis");
  const locale = useLocale();
  return (
    <section aria-labelledby="kpis" className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[22px]">
      <div className="flex flex-col gap-1">
        <h2 id="kpis" className="m-0 text-lg font-semibold text-ink">
          {t("title")}
        </h2>
        <p className="m-0 text-sm text-muted">{t("subtitle")}</p>
      </div>
      <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((kpi) => (
          <li key={kpi.kpi_id} className="flex flex-col gap-1.5 rounded-control border border-line p-3.5">
            <span className="text-[13px] text-muted">{kpi.name}</span>
            <span className="font-mono text-xl font-medium text-ink">{value(locale, kpi)}</span>
            <span className="text-[13px] leading-relaxed text-text">{kpi.definition}</span>
            <span className="text-xs text-muted">
              {t("owner", { owner: t(`owners.${kpi.owner}`) })} · <code className="font-mono">{kpi.kpi_id}</code>
            </span>
            {kpi.formula_sql && (
              <details className="text-xs">
                <summary className="min-h-touch cursor-pointer content-center text-primary">{t("formula")}</summary>
                <code className="block whitespace-pre-wrap break-words rounded-chip bg-ground p-2 font-mono text-text">
                  {kpi.formula_sql}
                </code>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
