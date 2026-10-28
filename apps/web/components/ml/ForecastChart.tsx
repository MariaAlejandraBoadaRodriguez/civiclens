"use client";

import { useLocale, useTranslations } from "next-intl";
import { DataTable } from "@/components/ui/DataTable";
import type { ForecastPoint } from "@/lib/api-types";
import { formatCompact } from "@/lib/format";

const W = 720;
const H = 260;
const PAD = { top: 16, right: 16, bottom: 32, left: 64 };

type Key = "actual" | "model" | "baseline";
const SERIES: { key: Key; stroke: string; dash?: string }[] = [
  { key: "actual", stroke: "var(--color-ink)" },
  { key: "model", stroke: "var(--color-primary)" },
  { key: "baseline", stroke: "var(--color-flag)", dash: "6 4" },
];

/** Monthly spend: actual history, then model and seasonal-naive baseline on the test window
 * and the next six months. The table below the chart holds the same numbers. */
export function ForecastChart({ points, testStart }: { points: ForecastPoint[]; testStart?: string }) {
  const t = useTranslations("ml.forecast.chart");
  const locale = useLocale();
  const values = points.flatMap((p) => [p.actual, p.model, p.baseline]).filter((v): v is number => v != null);
  const max = Math.max(...values, 1);
  const x = (i: number) => PAD.left + (i / Math.max(points.length - 1, 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => H - PAD.bottom - (v / max) * (H - PAD.top - PAD.bottom);
  const futureStart = points.findIndex((p) => p.actual == null);
  const testIndex = testStart ? points.findIndex((p) => p.month === testStart) : -1;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);

  const path = (key: Key) => {
    let d = "";
    let open = false;
    points.forEach((p, i) => {
      const v = p[key];
      if (v == null) {
        open = false;
        return;
      }
      d += `${open ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      open = true;
    });
    return d;
  };

  return (
    <figure className="m-0 flex flex-col gap-3">
      <ul className="m-0 flex list-none flex-wrap gap-4 p-0 text-[13px]">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <svg width="24" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="24" y2="4" stroke={s.stroke} strokeWidth="2.5" strokeDasharray={s.dash} />
            </svg>
            {t(`legend.${s.key}`)}
          </li>
        ))}
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="forecast-chart-title" className="h-auto w-full">
        <title id="forecast-chart-title">{t("title")}</title>
        {futureStart > 0 && (
          <rect
            x={x(futureStart)}
            y={PAD.top}
            width={W - PAD.right - x(futureStart)}
            height={H - PAD.top - PAD.bottom}
            fill="var(--color-subtle)"
          />
        )}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--color-line)" strokeWidth="1" />
            <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--color-muted)">
              {formatCompact(locale, v)}
            </text>
          </g>
        ))}
        {testIndex > 0 && (
          <g>
            <line
              x1={x(testIndex)}
              x2={x(testIndex)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="var(--color-muted)"
              strokeDasharray="2 3"
            />
            <text x={x(testIndex) + 4} y={PAD.top + 10} fontSize="11" fill="var(--color-muted)">
              {t("test")}
            </text>
          </g>
        )}
        {futureStart > 0 && (
          <text x={x(futureStart) + 4} y={PAD.top + 24} fontSize="11" fill="var(--color-muted)">
            {t("future")}
          </text>
        )}
        {points.map((p, i) =>
          i % 6 === 0 ? (
            <text key={p.month} x={x(i)} y={H - 10} textAnchor="middle" fontSize="11" fill="var(--color-muted)">
              {p.month}
            </text>
          ) : null,
        )}
        {SERIES.map((s) => (
          <path
            key={s.key}
            d={path(s.key)}
            fill="none"
            stroke={s.stroke}
            strokeWidth="2.5"
            strokeDasharray={s.dash}
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <figcaption className="text-[13px] text-muted">{t("caption")}</figcaption>
      <details className="text-sm">
        <summary className="min-h-touch cursor-pointer content-center text-primary">{t("table")}</summary>
        <DataTable
          caption={t("title")}
          captionHidden
          minWidth={420}
          rows={points}
          rowKey={(p) => p.month}
          columns={[
            { key: "month", header: t("month"), cell: (p) => p.month, mono: true },
            ...SERIES.map((s) => ({
              key: s.key,
              header: t(`legend.${s.key}`),
              align: "right" as const,
              mono: true,
              cell: (p: ForecastPoint) => (p[s.key] == null ? "—" : formatCompact(locale, p[s.key] as number, "CAD")),
            })),
          ]}
        />
      </details>
    </figure>
  );
}
