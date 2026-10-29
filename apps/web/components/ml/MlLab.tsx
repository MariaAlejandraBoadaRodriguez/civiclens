"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Contributions } from "@/components/ml/Contributions";
import { ForecastChart } from "@/components/ml/ForecastChart";
import { ModelCard } from "@/components/ml/ModelCard";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { KpiTile } from "@/components/ui/KpiTile";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { PUBLIC_API_URL } from "@/lib/api";
import type { ForecastResult, Job, Problem, RedFlagItem, RedFlagResult } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDate, formatNumber, formatPercent } from "@/lib/format";

type ModelType = "red_flags" | "forecast";
type Status = { state: "idle" | "running" } | { state: "error"; problem: Problem | null };

/** Run a model as a job, poll it, then load the localized latest result. */
function useModel<T>(model: ModelType, datasetRef: string, initial: T | null) {
  const locale = useLocale();
  const [result, setResult] = useState<T | null>(initial);
  const [status, setStatus] = useState<Status>({ state: "idle" });
  const headers = useMemo(() => ({ "Accept-Language": locale, "Content-Type": "application/json" }), [locale]);

  const run = useCallback(async () => {
    setStatus({ state: "running" });
    try {
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/models/${model}/run`, {
        method: "POST",
        headers,
        body: JSON.stringify({ dataset_id: datasetRef }),
      });
      const body = await res.json();
      if (!res.ok) return setStatus({ state: "error", problem: body as Problem });
      const job = body as Job;
      for (let n = 0; n < 120; n += 1) {
        await new Promise((r) => setTimeout(r, 1000));
        const state = (await (await fetch(`${PUBLIC_API_URL}/api/v1/jobs/${job.id}`, { headers })).json()) as Job;
        if (state.status === "failed") return setStatus({ state: "error", problem: state.error ?? null });
        if (state.status === "succeeded") break;
      }
      const latest = await fetch(`${PUBLIC_API_URL}/api/v1/models/${model}/latest?dataset_id=${datasetRef}`, { headers });
      if (!latest.ok) return setStatus({ state: "error", problem: (await latest.json()) as Problem });
      setResult((await latest.json()) as T);
      setStatus({ state: "idle" });
    } catch {
      setStatus({ state: "error", problem: null });
    }
  }, [model, datasetRef, headers]);

  useEffect(() => {
    if (initial === null) void run();
  }, [initial, run]);

  return { result, status, run };
}

function RunButton({ status, onRun }: { status: Status; onRun: () => void }) {
  const t = useTranslations("ml");
  return (
    <Button variant="secondary" onClick={onRun} disabled={status.state === "running"}>
      {status.state === "running" ? t("running") : t("rerun")}
    </Button>
  );
}

function StatusMessage({ status }: { status: Status }) {
  const t = useTranslations("ml");
  if (status.state !== "error") return null;
  return (
    <Alert variant="warning" title={status.problem?.title ?? t("unreachable")} titleId="model-error">
      {status.problem?.detail && <p className="m-0">{status.problem.detail}</p>}
    </Alert>
  );
}

function RedFlags({ datasetRef, initial }: { datasetRef: string; initial: RedFlagResult | null }) {
  const t = useTranslations("ml.flags");
  const locale = useLocale();
  const { result, status, run } = useModel<RedFlagResult>("red_flags", datasetRef, initial);
  const [selected, setSelected] = useState(1);
  const [showAll, setShowAll] = useState(false);
  const [reviewed, setReviewed] = useState<Set<string>>(new Set(initial?.reviewed ?? []));

  useEffect(() => setReviewed(new Set(result?.reviewed ?? [])), [result]);

  async function toggle(item: RedFlagItem) {
    const next = !reviewed.has(item.contract_id);
    const res = await fetch(`${PUBLIC_API_URL}/api/v1/models/red_flags/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept-Language": locale },
      body: JSON.stringify({ dataset_id: datasetRef, contract_id: item.contract_id, reviewed: next }),
    }).catch(() => null);
    if (res?.ok) setReviewed(new Set(((await res.json()) as { reviewed: string[] }).reviewed));
  }

  if (!result) {
    return (
      <div className="flex flex-col gap-4">
        <p className="m-0 text-[15px]" aria-live="polite">
          {t("training")}
        </p>
        <StatusMessage status={status} />
        <SkeletonGroup lines={6} />
      </div>
    );
  }
  const labels = Object.fromEntries(result.card.features.map((f) => [f.id, f.label]));
  const explained = result.items.find((i) => i.rank === selected && i.contributions) ?? result.items[0];
  return (
    <div className="flex flex-wrap items-start gap-5">
      <ModelCard
        card={result.card}
        id="card-red-flags"
        actions={
          <div className="flex flex-col gap-2">
            <RunButton status={status} onRun={run} />
            <StatusMessage status={status} />
          </div>
        }
      />
      <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
        <section aria-labelledby="flags" className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[18px]">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="flags" className="m-0 text-lg font-semibold text-ink">
              {t("title")}
            </h2>
            <span className="text-[13px] text-muted">
              {t("count", { flagged: result.flagged, contracts: result.contracts })}
            </span>
          </div>
          <p className="m-0 text-[13px] text-muted">{result.card.flagged_rule}</p>
          {result.items.length === 0 ? (
            <p className="m-0 text-sm">{t("none")}</p>
          ) : (
            <div className="relative overflow-x-auto" tabIndex={0} role="region" aria-label={t("tableRegion")}>
              <table className="w-full min-w-[560px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-muted">
                    <th scope="col" className="px-2 py-2.5 font-medium">
                      {t("score")}
                    </th>
                    <th scope="col" className="px-2 py-2.5 font-medium">
                      {t("contract")}
                    </th>
                    <th scope="col" className="px-2 py-2.5 font-medium">
                      {t("why")}
                    </th>
                    <th scope="col" className="px-2 py-2.5 font-medium">
                      <span className="sr-only">{t("action")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.slice(0, showAll ? undefined : 10).map((item) => {
                    const done = reviewed.has(item.contract_id);
                    return (
                      <tr key={item.contract_id} className={cn("border-b border-subtle align-top last:border-0", done && "opacity-60")}>
                        <td className="px-2 py-2.5 font-mono">{formatNumber(locale, item.score, 2)}</td>
                        <td className="max-w-[22rem] px-2 py-2.5">
                          <span className="block break-words font-medium">
                            {item.entity_name ?? "—"} → {item.supplier_name ?? "—"}
                          </span>
                          <span className="block text-[13px] text-muted">
                            {formatCurrency(locale, item.amount_cad, "CAD", 0)} · {formatDate(locale, item.signed_date, "short")}
                          </span>
                          <span className="block break-all font-mono text-xs text-muted">{item.contract_id}</span>
                        </td>
                        <td className="px-2 py-2.5">
                          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                            {item.reasons.map((r) => (
                              <li key={r} className="rounded-chip bg-flag-tint px-2 py-1 text-xs text-flag-text">
                                {result.reason_labels[r] ?? r}
                              </li>
                            ))}
                          </ul>
                          {item.contributions && (
                            <button
                              type="button"
                              onClick={() => setSelected(item.rank)}
                              aria-pressed={explained?.rank === item.rank}
                              className="mt-1 min-h-touch text-left text-[13px] text-primary underline-offset-4 hover:underline aria-pressed:font-medium"
                            >
                              {t("explain")}
                            </button>
                          )}
                        </td>
                        <td className="px-2 py-2.5 text-right">
                          <Button
                            variant="secondary"
                            className="whitespace-nowrap px-3 py-2 text-[13px]"
                            aria-pressed={done}
                            onClick={() => void toggle(item)}
                          >
                            {done ? t("reviewed") : t("markReviewed")}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {result.items.length > 10 && (
            <button
              type="button"
              aria-expanded={showAll}
              onClick={() => setShowAll((v) => !v)}
              className="min-h-touch self-start text-sm text-primary underline-offset-4 hover:underline"
            >
              {showAll ? t("showFewer") : t("showAll", { n: result.items.length })}
            </button>
          )}
        </section>
        {explained?.contributions && <Contributions item={explained} featureLabels={labels} />}
      </div>
    </div>
  );
}

function Forecast({ datasetRef, initial }: { datasetRef: string; initial: ForecastResult | null }) {
  const t = useTranslations("ml.forecast");
  const locale = useLocale();
  const { result, status, run } = useModel<ForecastResult>("forecast", datasetRef, initial);
  if (!result) {
    return (
      <div className="flex flex-col gap-4">
        <p className="m-0 text-[15px]" aria-live="polite">
          {t("training")}
        </p>
        <StatusMessage status={status} />
        <SkeletonGroup lines={6} />
      </div>
    );
  }
  const m = result.metrics;
  const pct = (v?: number | null) => (v == null ? "—" : formatPercent(locale, v));
  return (
    <div className="flex flex-wrap items-start gap-5">
      <ModelCard
        card={result.card}
        id="card-forecast"
        actions={
          <div className="flex flex-col gap-2">
            <RunButton status={status} onRun={run} />
            <StatusMessage status={status} />
          </div>
        }
      />
      <section aria-labelledby="forecast" className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
        <div className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[18px]">
          <h2 id="forecast" className="m-0 text-lg font-semibold text-ink">
            {t("title")}
          </h2>
          {result.card.verdict && (
            <Alert variant={m.beats_baseline ? "info" : "warning"}>
              <p className="m-0 font-medium">{result.card.verdict}</p>
            </Alert>
          )}
          {result.status === "ok" && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <KpiTile label={t("mapeModel")} value={pct(m.mape_model)} />
                <KpiTile label={t("mapeBaseline")} value={pct(m.mape_baseline)} />
                <KpiTile
                  label={t("window")}
                  value={t("months", { n: result.test_months ?? 0 })}
                  note={t("windowNote", { months: result.months })}
                />
              </div>
              <ForecastChart points={result.series} testStart={result.test_start} />
            </>
          )}
          {result.card.dropped && <p className="m-0 text-[13px] text-muted">{result.card.dropped}</p>}
          <p className="m-0 text-[13px] text-muted">{t("mapeHelp")}</p>
        </div>
      </section>
    </div>
  );
}

export function MlLab({
  datasetRef,
  redFlags,
  forecast,
}: {
  datasetRef: string;
  redFlags: RedFlagResult | null;
  forecast: ForecastResult | null;
}) {
  const t = useTranslations("ml.tabs");
  return (
    <Tabs
      label={t("label")}
      items={[
        { value: "red_flags", label: t("redFlags"), content: <RedFlags datasetRef={datasetRef} initial={redFlags} /> },
        { value: "forecast", label: t("forecast"), content: <Forecast datasetRef={datasetRef} initial={forecast} /> },
        { value: "classifier", label: t("classifier"), content: null, disabled: true },
        { value: "segments", label: t("segments"), content: null, disabled: true },
      ]}
    />
  );
}
