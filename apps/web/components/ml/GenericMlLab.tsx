"use client";

import { useId, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Forecast, RunButton, StatusMessage, useModel } from "@/components/ml/MlLab";
import { ModelCard } from "@/components/ml/ModelCard";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { DataTable } from "@/components/ui/DataTable";
import { KpiTile } from "@/components/ui/KpiTile";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import type {
  AnomaliesResult,
  DataColumn,
  ForecastResult,
  SegmentsResult,
  TargetModelResult,
} from "@/lib/api-types";
import { formatNumber, formatPercent } from "@/lib/format";

/** Columns a target model can predict: flags, categories with up to 20 labels, quantities. */
function targetable(c: DataColumn): boolean {
  if (c.binary || c.kind === "boolean") return true;
  if (c.kind === "category") return c.distinct > 2 && c.distinct <= 20;
  return (c.kind === "number" || c.kind === "integer") && c.distinct > 2;
}

const RATIOS = new Set(["roc_auc", "average_precision", "accuracy", "precision", "recall", "positive_rate", "f1_macro", "r2"]);

function metric(locale: string, key: string, value: number): string {
  return RATIOS.has(key) ? formatNumber(locale, value, 3) : formatNumber(locale, value, 2);
}

function Waiting({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-[15px]" aria-live="polite">
        {text}
      </p>
      <SkeletonGroup lines={6} />
    </div>
  );
}

function Prediction({
  datasetRef,
  initial,
  columns,
}: {
  datasetRef: string;
  initial: TargetModelResult | null;
  columns: DataColumn[];
}) {
  const t = useTranslations("ml.generic.target");
  const locale = useLocale();
  const selectId = useId();
  const { result, status, run } = useModel<TargetModelResult>("target_model", datasetRef, initial);
  const options = columns.filter(targetable);
  const [target, setTarget] = useState<string>(result?.target ?? "");
  const chooser = (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-sm font-medium text-ink">
          {t("target")}
        </label>
        <select
          id={selectId}
          value={target || result?.target || ""}
          onChange={(e) => setTarget(e.target.value)}
          className="min-h-touch max-w-[320px] rounded-nav border border-line-strong bg-surface px-2 font-mono text-sm"
        >
          <option value="">{t("auto")}</option>
          {options.map((c) => (
            <option key={c.name} value={c.name}>
              {c.source} · {c.kind_label}
            </option>
          ))}
        </select>
      </div>
      <Button onClick={() => void run(target ? { target } : undefined)} disabled={status.state === "running"}>
        {status.state === "running" ? t("training") : t("train")}
      </Button>
    </div>
  );
  if (!result) {
    return (
      <div className="flex flex-col gap-4">
        {chooser}
        <StatusMessage status={status} onRetry={() => void run()} />
        <Waiting text={t("trainingLong")} />
      </div>
    );
  }
  const ok = result.status === "ok";
  const m = result.metrics ?? {};
  const b = result.baseline_metrics ?? {};
  const labels = result.card.metric_labels ?? {};
  const shown = Object.keys(b).filter((k) => k in m);
  return (
    <div className="flex flex-wrap items-start gap-5">
      <ModelCard card={result.card} id="card-target" actions={<StatusMessage status={status} onRetry={() => void run()} />} />
      <section aria-labelledby="prediction" className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
        <div className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[18px]">
          <h2 id="prediction" className="m-0 text-lg font-semibold text-ink">
            {t("title")}
          </h2>
          {chooser}
          {result.card.verdict && (
            <Alert variant={ok && result.beats_baseline ? "info" : "warning"}>
              <p className="m-0 font-medium" data-testid="model-verdict">
                {result.card.verdict}
              </p>
            </Alert>
          )}
          {result.card.positive && <p className="m-0 text-sm text-muted">{result.card.positive}</p>}
          {ok && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {shown.map((k) => (
                <KpiTile
                  key={k}
                  label={labels[k] ?? k}
                  value={metric(locale, k, m[k])}
                  note={t("baseline", { value: metric(locale, k, b[k]) })}
                />
              ))}
            </div>
          )}
          {(result.leakage ?? []).length > 0 && (
            <Alert variant="warning" title={t("leakageTitle")}>
              <p className="m-0">{t("leakageBody", { columns: (result.leakage ?? []).map((l) => l.feature).join(", ") })}</p>
            </Alert>
          )}
        </div>
        {ok && (result.importance ?? []).length > 0 && (
          <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[18px]">
            <h3 className="m-0 text-base font-semibold text-ink">{t("importance")}</h3>
            <p className="m-0 text-[13px] text-muted">{t("importanceHelp")}</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0" data-testid="importance">
              {(result.importance ?? []).map((row) => (
                <li key={row.feature} className="grid grid-cols-[minmax(0,180px)_1fr_auto] items-center gap-3 text-sm">
                  <span className="truncate font-mono" title={row.label}>
                    {row.label}
                  </span>
                  <span className="h-2.5 rounded-full bg-subtle" aria-hidden="true">
                    <span className="block h-2.5 rounded-full bg-primary" style={{ width: `${Math.max(2, row.share * 100)}%` }} />
                  </span>
                  <span className="font-mono text-muted">{formatPercent(locale, row.share, 0)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {(result.fairness ?? []).map((f) => (
          <div key={f.attribute} className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[18px]" data-testid="fairness">
            <h3 className="m-0 text-base font-semibold text-ink">{t("fairness", { attribute: f.label })}</h3>
            <Alert variant={f.passes ? "info" : "warning"}>
              <p className="m-0">{f.verdict}</p>
            </Alert>
            <DataTable
              caption={t("fairness", { attribute: f.label })}
              captionHidden
              minWidth={520}
              rows={f.groups}
              rowKey={(g) => g.group}
              columns={[
                { key: "group", header: t("group"), mono: true, cell: (g) => g.group },
                { key: "rows", header: t("rows"), align: "right", mono: true, cell: (g) => formatNumber(locale, g.rows) },
                { key: "actual", header: t("actualRate"), align: "right", mono: true, cell: (g) => formatPercent(locale, g.actual_rate) },
                { key: "flagged", header: t("flaggedRate"), align: "right", mono: true, cell: (g) => formatPercent(locale, g.flagged_rate) },
                {
                  key: "tpr",
                  header: t("tpr"),
                  align: "right",
                  mono: true,
                  cell: (g) => (g.true_positive_rate == null ? "—" : formatPercent(locale, g.true_positive_rate)),
                },
              ]}
            />
          </div>
        ))}
      </section>
    </div>
  );
}

function Unusual({ datasetRef, initial }: { datasetRef: string; initial: AnomaliesResult | null }) {
  const t = useTranslations("ml.generic.anomalies");
  const locale = useLocale();
  const { result, status, run } = useModel<AnomaliesResult>("anomalies", datasetRef, initial);
  if (!result) {
    return (
      <>
        <StatusMessage status={status} onRetry={() => void run()} />
        <Waiting text={t("training")} />
      </>
    );
  }
  return (
    <div className="flex flex-wrap items-start gap-5">
      <ModelCard
        card={result.card}
        id="card-anomalies"
        actions={
          <div className="flex flex-col gap-2">
            <RunButton status={status} onRun={() => void run()} />
            <StatusMessage status={status} onRetry={() => void run()} />
          </div>
        }
      />
      <section aria-labelledby="unusual" className="flex min-w-0 flex-[2_1_520px] flex-col gap-4 rounded-card border border-line bg-surface p-[18px]">
        <h2 id="unusual" className="m-0 text-lg font-semibold text-ink">
          {t("title")}
        </h2>
        {result.card.verdict && (
          <Alert variant={result.status === "ok" ? "info" : "warning"}>
            <p className="m-0 font-medium">{result.card.verdict}</p>
          </Alert>
        )}
        {result.top && result.top.length > 0 && (
          <DataTable
            caption={t("title")}
            captionHidden
            minWidth={560}
            rows={result.top}
            rowKey={(r) => String(r.row)}
            columns={[
              { key: "row", header: t("row"), align: "right", mono: true, cell: (r) => formatNumber(locale, r.row) },
              { key: "why", header: t("why"), cell: (r) => r.why },
              {
                key: "labels",
                header: t("context"),
                mono: true,
                cell: (r) => (
                  <span className="text-[13px] text-muted">
                    {Object.values(r.labels)
                      .filter((v): v is string => Boolean(v))
                      .join(" · ") || "—"}
                  </span>
                ),
              },
            ]}
          />
        )}
      </section>
    </div>
  );
}

function Segments({ datasetRef, initial }: { datasetRef: string; initial: SegmentsResult | null }) {
  const t = useTranslations("ml.generic.segments");
  const locale = useLocale();
  const { result, status, run } = useModel<SegmentsResult>("segments", datasetRef, initial);
  if (!result) {
    return (
      <>
        <StatusMessage status={status} onRetry={() => void run()} />
        <Waiting text={t("training")} />
      </>
    );
  }
  return (
    <div className="flex flex-wrap items-start gap-5">
      <ModelCard
        card={result.card}
        id="card-segments"
        actions={
          <div className="flex flex-col gap-2">
            <RunButton status={status} onRun={() => void run()} />
            <StatusMessage status={status} onRetry={() => void run()} />
          </div>
        }
      />
      <section aria-labelledby="segments" className="flex min-w-0 flex-[2_1_520px] flex-col gap-4 rounded-card border border-line bg-surface p-[18px]">
        <h2 id="segments" className="m-0 text-lg font-semibold text-ink">
          {t("title")}
        </h2>
        {result.card.verdict && (
          <Alert variant="warning">
            <p className="m-0 font-medium">{result.card.verdict}</p>
          </Alert>
        )}
        <ul className="m-0 flex list-none flex-col gap-3 p-0" data-testid="segments">
          {(result.segments ?? []).map((s) => (
            <li key={s.segment} className="flex flex-col gap-2 rounded-control border border-line p-3.5">
              <span className="flex items-center gap-3">
                <span className="h-2.5 flex-1 rounded-full bg-subtle" aria-hidden="true">
                  <span className="block h-2.5 rounded-full bg-primary" style={{ width: `${Math.max(2, s.share * 100)}%` }} />
                </span>
                <span className="font-mono text-sm text-muted">
                  {t("rows", { rows: formatNumber(locale, s.rows), share: formatPercent(locale, s.share, 0) })}
                </span>
              </span>
              <span className="text-sm leading-relaxed">{s.profile}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** ML lab for any table: prediction of a column the user picks, unusual rows, segments and a
 * forecast when the table has dates. Each tab trains when first opened. */
export function GenericMlLab({
  datasetRef,
  columns,
  initial,
}: {
  datasetRef: string;
  columns: DataColumn[];
  initial: {
    target: TargetModelResult | null;
    anomalies: AnomaliesResult | null;
    segments: SegmentsResult | null;
    forecast: ForecastResult | null;
  };
}) {
  const t = useTranslations("ml.tabs");
  return (
    <Tabs
      label={t("label")}
      items={[
        {
          value: "target_model",
          label: t("prediction"),
          content: <Prediction datasetRef={datasetRef} initial={initial.target} columns={columns} />,
        },
        { value: "anomalies", label: t("anomalies"), content: <Unusual datasetRef={datasetRef} initial={initial.anomalies} /> },
        { value: "segments", label: t("segmentsAny"), content: <Segments datasetRef={datasetRef} initial={initial.segments} /> },
        { value: "forecast", label: t("forecastAny"), content: <Forecast datasetRef={datasetRef} initial={initial.forecast} /> },
      ]}
    />
  );
}
