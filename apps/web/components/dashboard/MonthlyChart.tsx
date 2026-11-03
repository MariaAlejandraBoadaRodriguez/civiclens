"use client";

import { useLocale, useTranslations } from "next-intl";
import { DataTable } from "@/components/ui/DataTable";
import type { Dashboard } from "@/lib/api-types";
import { INTL_LOCALE, formatCompact } from "@/lib/format";
import type { Locale } from "@/i18n/routing";

const W = 720;
const H = 220;
const PAD = { top: 18, right: 8, bottom: 26, left: 8 };

export function monthLabel(locale: string, month: string, style: "short" | "long" = "short") {
  const [y, m] = month.split("-").map(Number);
  return new Intl.DateTimeFormat(INTL_LOCALE[locale as Locale] ?? "en-CA", {
    month: style,
    year: style === "long" || m === 1 ? "numeric" : undefined,
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, 1)));
}

/** Monthly spend in CAD; the peak month is drawn in the attention colour when it stands out. */
export function MonthlyChart({ monthly, peak }: Pick<Dashboard, "monthly" | "peak">) {
  const t = useTranslations("dashboard.monthly");
  const locale = useLocale();
  const max = Math.max(...monthly.map((m) => m.spend), 1);
  const step = (W - PAD.left - PAD.right) / Math.max(monthly.length, 1);
  const every = Math.max(1, Math.ceil(monthly.length / 12));
  const first = monthly[0]?.month;
  const last = monthly[monthly.length - 1]?.month;
  const summary =
    first && last
      ? t("chartLabel", { first: monthLabel(locale, first, "long"), last: monthLabel(locale, last, "long") })
      : t("title");

  return (
    <figure className="m-0 flex flex-col gap-3">
      {/* Below ~520 px the labels would shrink unreadably: the chart scrolls in its box instead. */}
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={summary}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="monthly-chart-title" className="h-auto w-full min-w-[520px]">
        <title id="monthly-chart-title">{summary}</title>
        <text x={PAD.left} y={11} fontSize="11" fill="var(--color-muted)">
          {formatCompact(locale, max, "CAD")}
        </text>
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} stroke="var(--color-line-strong)" />
        {monthly.map((m, i) => {
          const h = ((H - PAD.top - PAD.bottom) * m.spend) / max;
          const isPeak = Boolean(peak?.is_peak && peak.month === m.month);
          return (
            <g key={m.month}>
              <rect
                x={PAD.left + i * step + step * 0.14}
                y={H - PAD.bottom - h}
                width={step * 0.72}
                height={h}
                rx="2"
                fill={isPeak ? "var(--color-flag)" : "var(--color-primary)"}
                data-peak={isPeak || undefined}
              >
                <title>{t("bar", { month: monthLabel(locale, m.month, "long"), value: formatCompact(locale, m.spend, "CAD") })}</title>
              </rect>
              {i % every === 0 && (
                <text x={PAD.left + i * step + step / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--color-muted)">
                  {monthLabel(locale, m.month)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      </div>
      <details className="text-sm">
        <summary className="min-h-touch cursor-pointer content-center text-primary">{t("table")}</summary>
        <DataTable
          caption={summary}
          captionHidden
          minWidth={320}
          rows={monthly}
          rowKey={(m) => m.month}
          columns={[
            { key: "month", header: t("month"), cell: (m) => monthLabel(locale, m.month, "long") },
            { key: "spend", header: t("spend"), align: "right", mono: true, cell: (m) => formatCompact(locale, m.spend, "CAD") },
            { key: "contracts", header: t("contracts"), align: "right", mono: true, cell: (m) => String(m.contracts) },
          ]}
        />
      </details>
    </figure>
  );
}
