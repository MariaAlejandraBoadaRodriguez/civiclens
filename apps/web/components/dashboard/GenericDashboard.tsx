"use client";

import { useId, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { Button } from "@/components/ui/Button";
import { DataTable } from "@/components/ui/DataTable";
import { KpiTile } from "@/components/ui/KpiTile";
import type { ChartResult, Kpi, Overview, OverviewSection } from "@/lib/api-types";
import { apiRequest, type ApiFailure } from "@/lib/apiClient";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

type Unit = OverviewSection["unit"];

export function valueText(locale: string, value: number | null, unit: Unit): string {
  if (value === null) return "—";
  if (unit === "ratio") return formatPercent(locale, value);
  if (unit === "r") return formatNumber(locale, value, 2);
  if (unit === "amount" || Math.abs(value) >= 100_000) return formatCompact(locale, value);
  return formatNumber(locale, value, Number.isInteger(value) ? 0 : 2);
}

function kpiText(locale: string, kpi: Kpi): string {
  if (kpi.value === null) return "—";
  if (kpi.unit === "ratio") return formatPercent(locale, kpi.value);
  return valueText(locale, kpi.value, kpi.unit === "amount" ? "amount" : "count");
}

/** Horizontal bars (categories, bins) or a line (time): the numbers stay readable as text. */
function Bars({ rows, unit, caption }: { rows: { label: string; value: number | null }[]; unit: Unit; caption: string }) {
  const locale = useLocale();
  const top = Math.max(...rows.map((r) => Math.abs(r.value ?? 0)), 1);
  return (
    <figure className="m-0 flex flex-col gap-1.5" aria-label={caption}>
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[minmax(0,200px)_1fr_auto] items-center gap-3 text-[13px]">
          <span className="truncate" title={r.label}>
            {r.label}
          </span>
          <span className="h-2.5 rounded-full bg-subtle" aria-hidden="true">
            <span className="block h-2.5 rounded-full bg-primary" style={{ width: `${Math.max(1, (100 * Math.abs(r.value ?? 0)) / top)}%` }} />
          </span>
          <span className="font-mono text-muted">{valueText(locale, r.value, unit)}</span>
        </div>
      ))}
    </figure>
  );
}

function Line({ rows, unit, caption }: { rows: { label: string; value: number | null }[]; unit: Unit; caption: string }) {
  const locale = useLocale();
  const t = useTranslations("dashboard.any");
  const values = rows.map((r) => r.value ?? 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const w = 600;
  const h = 160;
  const x = (i: number) => (rows.length < 2 ? 0 : (i / (rows.length - 1)) * w);
  const y = (v: number) => h - ((v - min) / (max - min || 1)) * h;
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <figure className="m-0 flex flex-col gap-1">
      <svg viewBox={`0 0 ${w} ${h + 4}`} role="img" aria-label={caption} className="h-auto w-full">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
      </svg>
      <figcaption className="flex justify-between font-mono text-xs text-muted">
        <span>{rows[0]?.label}</span>
        <span>{t("range", { min: valueText(locale, min, unit), max: valueText(locale, max, unit) })}</span>
        <span>{rows[rows.length - 1]?.label}</span>
      </figcaption>
    </figure>
  );
}

function Section({ s }: { s: OverviewSection }) {
  const t = useTranslations("dashboard.any");
  return (
    <section
      aria-labelledby={`section-${s.id}`}
      className="flex min-w-0 flex-[1_1_440px] flex-col gap-3 rounded-card border border-line bg-surface p-[18px]"
      data-testid="overview-section"
    >
      <h2 id={`section-${s.id}`} className="m-0 text-base font-semibold text-ink">
        {s.title}
      </h2>
      <p className="m-0 text-[15px] font-medium leading-relaxed" data-testid="finding">
        {s.finding}
      </p>
      {s.chart === "line" ? <Line rows={s.rows} unit={s.unit} caption={s.title} /> : <Bars rows={s.rows.slice(0, 12)} unit={s.unit} caption={s.title} />}
      {s.sql && (
        <details className="text-xs">
          <summary className="min-h-touch cursor-pointer content-center text-primary">{t("sql")}</summary>
          <code className="block whitespace-pre-wrap break-words rounded-chip bg-ground p-2 font-mono text-text">{s.sql}</code>
        </details>
      )}
    </section>
  );
}

type BuilderState = { state: "idle" | "running" } | { state: "done"; result: ChartResult } | { state: "error"; error: ApiFailure };

/** "Build your own chart": metric, aggregation, dimension, one filter, chart type. */
function ChartBuilder({ datasetRef, overview }: { datasetRef: string; overview: Overview }) {
  const t = useTranslations("dashboard.any.builder");
  const locale = useLocale();
  const ids = useId();
  const [dimension, setDimension] = useState(overview.dimensions[0]?.name ?? "");
  const [aggregation, setAggregation] = useState(overview.metrics.length ? "avg" : "count");
  const [metric, setMetric] = useState(overview.metrics[0]?.name ?? "");
  const [filterColumn, setFilterColumn] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [chartType, setChartType] = useState<"bar" | "line" | "table">("bar");
  const [run, setRun] = useState<BuilderState>({ state: "idle" });
  if (!overview.dimensions.length) return null;

  async function submit() {
    setRun({ state: "running" });
    const res = await apiRequest<ChartResult>(`/api/v1/datasets/${encodeURIComponent(datasetRef)}/chart`, {
      locale,
      json: {
        dimension,
        aggregation,
        metric: aggregation === "count" ? null : metric,
        chart_type: chartType,
        filters: filterColumn && filterValue ? [{ column: filterColumn, op: "eq", values: [filterValue] }] : [],
      },
    });
    setRun(res.ok ? { state: "done", result: res.data } : { state: "error", error: res.error });
  }

  const select = "min-h-touch w-full rounded-nav border border-line-strong bg-surface px-2 text-sm";
  const field = (id: string, label: string, control: React.ReactNode) => (
    <div className="flex min-w-[160px] flex-1 flex-col gap-1.5">
      <label htmlFor={`${ids}-${id}`} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {control}
    </div>
  );
  const unit: Unit = aggregation === "count" ? "count" : "amount";
  return (
    <section aria-labelledby="chart-builder" className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[18px]">
      <div className="flex flex-col gap-1">
        <h2 id="chart-builder" className="m-0 text-lg font-semibold text-ink">
          {t("title")}
        </h2>
        <p className="m-0 text-sm text-muted">{t("hint")}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {field(
          "agg",
          t("aggregation"),
          <select id={`${ids}-agg`} value={aggregation} onChange={(e) => setAggregation(e.target.value)} className={select}>
            {["count", "sum", "avg", "median", "min", "max"]
              .filter((a) => a === "count" || overview.metrics.length > 0)
              .map((a) => (
                <option key={a} value={a}>
                  {t(`aggregations.${a}`)}
                </option>
              ))}
          </select>,
        )}
        {aggregation !== "count" &&
          field(
            "metric",
            t("metric"),
            <select id={`${ids}-metric`} value={metric} onChange={(e) => setMetric(e.target.value)} className={select}>
              {overview.metrics.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.source}
                </option>
              ))}
            </select>,
          )}
        {field(
          "dim",
          t("dimension"),
          <select id={`${ids}-dim`} value={dimension} onChange={(e) => setDimension(e.target.value)} className={select}>
            {overview.dimensions.map((d) => (
              <option key={d.name} value={d.name}>
                {d.source}
              </option>
            ))}
          </select>,
        )}
        {field(
          "fcol",
          t("filterColumn"),
          <select id={`${ids}-fcol`} value={filterColumn} onChange={(e) => setFilterColumn(e.target.value)} className={select}>
            <option value="">{t("noFilter")}</option>
            {overview.dimensions.map((d) => (
              <option key={d.name} value={d.name}>
                {d.source}
              </option>
            ))}
          </select>,
        )}
        {filterColumn &&
          field(
            "fval",
            t("filterValue"),
            <input id={`${ids}-fval`} value={filterValue} onChange={(e) => setFilterValue(e.target.value)} className={select} />,
          )}
        {field(
          "type",
          t("chartType"),
          <select id={`${ids}-type`} value={chartType} onChange={(e) => setChartType(e.target.value as "bar" | "line" | "table")} className={select}>
            {(["bar", "line", "table"] as const).map((c) => (
              <option key={c} value={c}>
                {t(`types.${c}`)}
              </option>
            ))}
          </select>,
        )}
      </div>
      <div>
        <Button onClick={() => void submit()} disabled={run.state === "running"}>
          {run.state === "running" ? t("running") : t("draw")}
        </Button>
      </div>
      <div aria-live="polite" data-testid="custom-chart">
        {run.state === "error" && <ApiErrorNotice error={run.error} />}
        {run.state === "done" &&
          (run.result.rows.length === 0 ? (
            <p className="m-0 text-sm text-muted">{t("empty")}</p>
          ) : run.result.chart === "table" ? (
            <DataTable
              caption={t("title")}
              captionHidden
              rows={run.result.rows}
              rowKey={(r) => r.label}
              columns={[
                { key: "label", header: run.result.dimension, cell: (r) => r.label },
                { key: "value", header: t(`aggregations.${run.result.aggregation}`), align: "right", mono: true, cell: (r) => valueText(locale, r.value, unit) },
              ]}
            />
          ) : run.result.chart === "line" ? (
            <Line rows={run.result.rows} unit={unit} caption={t("title")} />
          ) : (
            <Bars rows={run.result.rows} unit={unit} caption={t("title")} />
          ))}
      </div>
    </section>
  );
}

export function GenericDashboard({ overview, datasetRef }: { overview: Overview; datasetRef: string }) {
  const t = useTranslations("dashboard.any");
  const locale = useLocale();
  const q = overview.quality;
  return (
    <div className="flex flex-col gap-6">
      <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-4">
        {overview.kpis.map((k) => (
          <li key={k.kpi_id} data-testid="kpi-tile">
            <KpiTile label={k.name} value={kpiText(locale, k)} note={k.definition} />
          </li>
        ))}
      </ul>
      <p className="m-0 rounded-card border border-line bg-surface px-[18px] py-3 text-[15px]" data-testid="quality">
        {q.after !== null && q.after !== undefined
          ? t("qualityAfter", { before: q.before ?? 0, after: q.after })
          : t("qualityBefore", { before: q.before ?? 0 })}
      </p>
      <div className="flex flex-wrap gap-5">
        {overview.sections.map((s) => (
          <Section key={s.id} s={s} />
        ))}
      </div>
      <ChartBuilder datasetRef={datasetRef} overview={overview} />
    </div>
  );
}
