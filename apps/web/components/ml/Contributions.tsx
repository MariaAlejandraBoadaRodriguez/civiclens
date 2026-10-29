"use client";

import { useLocale, useTranslations } from "next-intl";
import type { RedFlagItem } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

/** SHAP feature contributions: orange bars push the anomaly score up, blue bars pull it down. */
export function Contributions({ item, featureLabels }: { item: RedFlagItem; featureLabels: Record<string, string> }) {
  const t = useTranslations("ml.flags.shap");
  const locale = useLocale();
  const contributions = (item.contributions ?? []).slice(0, 6);
  const max = Math.max(...contributions.map((c) => Math.abs(c.value)), 0.0001);
  const signed = (v: number) => `${v >= 0 ? "+" : "−"}${formatNumber(locale, Math.abs(v), 2)}`;
  return (
    <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[18px]">
      <h3 className="m-0 text-[15px] font-semibold text-ink">
        {t("title", { rank: item.rank, score: formatNumber(locale, item.score, 2) })}
      </h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {contributions.map((c) => (
          <li key={c.feature} className="grid grid-cols-[minmax(0,12rem)_1fr_3.5rem] items-center gap-3 text-[13px]">
            <span className="truncate font-mono" title={featureLabels[c.feature]}>
              {c.feature}
            </span>
            <span className="relative h-3 rounded-chip bg-track" aria-hidden="true">
              <span
                className={cn("absolute inset-y-0 left-0 rounded-chip", c.value >= 0 ? "bg-flag" : "bg-primary")}
                style={{ width: `${(Math.abs(c.value) / max) * 100}%` }}
              />
            </span>
            <span className="text-right font-mono">
              {signed(c.value)}
              <span className="sr-only"> {c.value >= 0 ? t("up") : t("down")}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="m-0 text-[13px] text-muted">
        {t("legend", { base: formatNumber(locale, item.base_value ?? 0, 2) })}
      </p>
    </div>
  );
}
