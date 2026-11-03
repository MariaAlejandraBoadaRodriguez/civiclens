import { useLocale, useTranslations } from "next-intl";
import type { DashboardJurisdiction } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatCompact, formatNumber } from "@/lib/format";

/** Spend by jurisdiction, one currency (CAD), bars relative to the largest. */
export function JurisdictionBars({ items, selected = [] }: { items: DashboardJurisdiction[]; selected?: string[] }) {
  const t = useTranslations("dashboard.jurisdictions");
  const locale = useLocale();
  return (
    <ul className="m-0 flex list-none flex-col gap-3.5 p-0 text-sm">
      {items.map((j) => (
        <li
          key={j.dataset_id}
          className="flex flex-col gap-1.5"
          data-testid="jurisdiction-row"
          data-selected={selected.includes(j.dataset_id) || undefined}
        >
          <div className="flex flex-wrap justify-between gap-x-3">
            <span className={cn("min-w-0 break-words", selected.includes(j.dataset_id) && "font-semibold text-ink")}>
              {j.label}
              {selected.includes(j.dataset_id) && <span className="sr-only">{t("selected")}</span>}
            </span>
            <span className="font-mono">{formatCompact(locale, j.spend, "CAD")}</span>
          </div>
          <div className="h-2.5 rounded-[3px] bg-subtle" aria-hidden="true">
            <div className="h-2.5 rounded-[3px] bg-primary" style={{ width: `${Math.round(j.share_of_max * 100)}%` }} />
          </div>
          <span className="text-xs text-muted">{t("contracts", { n: formatNumber(locale, j.contracts, 0) })}</span>
        </li>
      ))}
    </ul>
  );
}
