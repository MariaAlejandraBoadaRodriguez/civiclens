"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { BeforeAfter } from "@/components/ui/BeforeAfter";
import { Button, ButtonLink } from "@/components/ui/Button";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { IssueCard } from "@/components/ui/IssueCard";
import { OptionRadio } from "@/components/ui/OptionRadio";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { PUBLIC_API_URL } from "@/lib/api";
import type { ApplyResult, Issue, IssuesResponse, Job, Problem, RecipeStep } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { cellText, kpiText } from "./format";

type Status = "done" | "skipped";
type Code = { pandas: string; sql: string; json: string };
type Run =
  | { state: "idle" }
  | { state: "saving" | "applying" }
  | { state: "done"; result: ApplyResult; version: number }
  | { state: "error"; problem: Pick<Problem, "title" | "detail"> };

const FORMATS = ["pandas", "sql", "json"] as const;
const joinDot = (parts: string[]) => parts.join(" · ");

function argSummary(step: RecipeStep): string {
  return Object.entries(step.args)
    .filter(([, v]) => typeof v !== "object" || v === null)
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(", ");
}

export function CleaningStudio({ data, datasetRef }: { data: IssuesResponse; datasetRef: string }) {
  const t = useTranslations("clean");
  const locale = useLocale();
  const params = useSearchParams();
  const router = useRouter();
  const issues = data.issues;
  const headers = useMemo(() => ({ "Accept-Language": locale, "Content-Type": "application/json" }), [locale]);

  const initial = Math.max(0, issues.findIndex((i) => i.issue_type === params.get("issue")));
  const [current, setCurrent] = useState(initial);
  const [choices, setChoices] = useState<Record<string, string>>(() =>
    Object.fromEntries(issues.map((i) => [i.issue_id, (i.options.find((o) => o.recommended) ?? i.options[0]).option_id])),
  );
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [learnMore, setLearnMore] = useState(false);
  const [code, setCode] = useState<Code | null>(null);
  const [run, setRun] = useState<Run>({ state: "idle" });

  const issue: Issue | undefined = issues[current];
  const option = issue?.options.find((o) => o.option_id === choices[issue.issue_id]) ?? issue?.options[0];
  const resolved = issues.filter((i) => status[i.issue_id]).length;

  // Recipe = decided issues in pipeline order, plus the current choice shown as pending.
  const decided = issues.flatMap((i) =>
    status[i.issue_id] === "done" ? (i.options.find((o) => o.option_id === choices[i.issue_id])?.steps ?? []) : [],
  );
  const pending = issue && !status[issue.issue_id] ? (option?.steps ?? []) : [];
  const recipe = useMemo(() => {
    const ordered: { step: RecipeStep; pending: boolean }[] = [];
    for (const i of issues) {
      const chosen = i.options.find((o) => o.option_id === choices[i.issue_id]);
      const isCurrent = i === issue && !status[i.issue_id];
      if (status[i.issue_id] === "done" || isCurrent) {
        for (const step of chosen?.steps ?? []) ordered.push({ step, pending: isCurrent });
      }
    }
    return ordered;
  }, [issues, choices, status, issue]);
  const steps = useMemo(() => recipe.map((r) => r.step), [recipe]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${PUBLIC_API_URL}/api/v1/recipes/preview`, {
          method: "POST",
          headers,
          body: JSON.stringify({ steps, columns: data.columns, name: data.dataset.slug ?? "recipe" }),
          signal: controller.signal,
        });
        if (res.ok) setCode((await res.json()) as Code);
      } catch {
        /* the panel keeps the previous code; the API may be waking up */
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [steps, headers, data.columns, data.dataset.slug]);

  function decide(next: Status) {
    if (!issue) return;
    const updated = { ...status, [issue.issue_id]: next };
    setStatus(updated);
    setLearnMore(false);
    const after = issues.findIndex((i, n) => n > current && !updated[i.issue_id]);
    const before = issues.findIndex((i) => !updated[i.issue_id]);
    setCurrent(after >= 0 ? after : before >= 0 ? before : current);
  }

  async function saveRecipe(): Promise<{ id: string; version: number } | null> {
    const name = `${data.dataset.slug ?? data.dataset.id} cleaning`;
    const res = await fetch(`${PUBLIC_API_URL}/api/v1/recipes`, {
      method: "POST",
      headers,
      body: JSON.stringify({ name, steps: decided, dataset_id: data.dataset.id }),
    });
    const body = await res.json();
    if (!res.ok) {
      setRun({ state: "error", problem: body as Problem });
      return null;
    }
    return body as { id: string; version: number };
  }

  async function saveAndApply() {
    setRun({ state: "saving" });
    try {
      const recipe = await saveRecipe();
      if (!recipe) return;
      setRun({ state: "applying" });
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/datasets/${datasetRef}/recipes/apply`, {
        method: "POST",
        headers,
        body: JSON.stringify({ recipe_id: recipe.id }),
      });
      const job = (await res.json()) as { id: string };
      for (let n = 0; n < 180; n += 1) {
        const state = (await (await fetch(`${PUBLIC_API_URL}/api/v1/jobs/${job.id}`, { headers })).json()) as Job;
        if (state.status === "succeeded") {
          setRun({ state: "done", result: state.result as unknown as ApplyResult, version: recipe.version });
          router.refresh(); // header chip: "Quality before → after"
          return;
        }
        if (state.status === "failed") {
          setRun({ state: "error", problem: state.error ?? { title: t("run.failed"), detail: "" } });
          return;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch {
      setRun({ state: "error", problem: { title: t("run.networkTitle"), detail: t("run.networkDetail") } });
    }
  }

  async function exportCode(format: (typeof FORMATS)[number]) {
    const recipe = await saveRecipe();
    if (!recipe) return;
    const a = document.createElement("a");
    a.href = `${PUBLIC_API_URL}/api/v1/recipes/${recipe.id}/export?format=${format}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const [format, setFormat] = useState<(typeof FORMATS)[number]>("pandas");
  const empty = t("preview.empty");
  const rows = (cells: (string | number | boolean | null)[][]) =>
    cells.map((row) =>
      row[row.length - 1] === "__removed__" ? t("preview.removed") : joinDot(row.map((c) => cellText(c, locale, empty))),
    );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start gap-5">
        <nav aria-label={t("list.label")} className="flex min-w-0 flex-[1_1_240px] flex-col gap-1 rounded-card border border-line bg-surface p-3">
          <p className="mx-2 mb-2 mt-1.5 text-[13px] font-medium text-muted">
            {t("list.resolved", { done: resolved, total: issues.length })}
          </p>
          <ol className="m-0 flex list-none flex-col gap-1 p-0">
            {issues.map((i, n) => {
              const s = status[i.issue_id];
              const active = n === current;
              return (
                <li key={i.issue_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setCurrent(n);
                      setLearnMore(false);
                    }}
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "flex min-h-touch w-full items-center justify-between gap-2 rounded-control px-2.5 text-left text-sm",
                      active ? "bg-primary-tint font-medium text-primary-dark" : "text-text hover:bg-ground",
                    )}
                  >
                    <span className="min-w-0 break-words">{i.title}</span>
                    <span
                      className={cn(
                        "shrink-0 text-[13px]",
                        s === "done" ? "text-success" : s === "skipped" ? "text-flag" : active ? "" : "text-muted",
                      )}
                    >
                      {s === "done" ? t("list.done") : s === "skipped" ? t("list.skipped") : active ? t("list.now") : t("list.todo")}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="min-w-0 flex-[999_1_520px]">
          {issue && option ? (
            <IssueCard
              id="issue-title"
              eyebrow={t("issue.eyebrow", { n: issue.position, total: issue.of, category: issue.category_label })}
              title={issue.title}
              found={issue.what}
              why={issue.why}
              options={
                <OptionRadio
                  legend={t("issue.legend")}
                  value={option.option_id}
                  onValueChange={(v) => setChoices((c) => ({ ...c, [issue.issue_id]: v }))}
                  options={issue.options.map((o) => ({
                    value: o.option_id,
                    label: o.recommended ? t("issue.recommended", { label: o.label }) : o.label,
                    hint: o.hint,
                  }))}
                />
              }
              preview={
                issue.preview_columns.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <p className="m-0 text-[13px] text-muted">
                      {t("preview.caption", { columns: issue.preview_columns.join(", "), rows: formatNumber(locale, issue.affected_rows) })}
                    </p>
                    <BeforeAfter
                      before={rows(issue.preview_before)}
                      after={rows(issue.preview_after[option.option_id] ?? issue.preview_before)}
                      afterLabel={option.label}
                    />
                  </div>
                ) : undefined
              }
              impact={
                issue.kpi_label
                  ? {
                      label: t("kpi.label", { kpi: issue.kpi_label }),
                      before: kpiText(issue.kpi_before, locale, t(`kpi.${issue.kpi_before?.reason ?? "unavailable"}`)),
                      after: kpiText(issue.kpi_after[option.option_id], locale, t(`kpi.${issue.kpi_after[option.option_id]?.reason ?? "unavailable"}`)),
                      note: issue.fx_note ?? (issue.kpi_before?.scope ? t("kpi.dominant", { currency: issue.kpi_before.currency ?? "" }) : t("kpi.assumption")),
                    }
                  : undefined
              }
              actions={
                <>
                  <Button onClick={() => decide("done")}>{t("issue.apply")}</Button>
                  <Button variant="secondary" onClick={() => decide("skipped")}>
                    {t("issue.skip")}
                  </Button>
                  <Button variant="ghost" aria-expanded={learnMore} aria-controls="learn-more" onClick={() => setLearnMore((v) => !v)}>
                    {t("issue.learnMore")}
                  </Button>
                  {learnMore && (
                    <p id="learn-more" className="m-0 basis-full rounded-panel bg-primary-soft p-3 text-sm text-primary-dark">
                      {issue.learn_more}
                    </p>
                  )}
                </>
              }
            />
          ) : (
            <p className="m-0 rounded-card border border-line bg-surface p-6 text-[15px]">{t("noIssues")}</p>
          )}
        </div>

        <section
          aria-labelledby="recipe-title"
          className="focus-on-dark flex min-w-0 flex-[1_1_280px] flex-col gap-3.5 rounded-card bg-ink p-5 text-code-text"
        >
          <h2 id="recipe-title" className="m-0 text-base font-semibold text-white">
            {run.state === "done" ? t("recipe.titleVersion", { version: run.version }) : t("recipe.titleDraft")}
          </h2>
          {steps.length === 0 ? (
            <p className="m-0 text-[13px] text-ink-dim">{t("recipe.empty")}</p>
          ) : (
            <ol className="m-0 flex flex-col gap-1.5 pl-[18px] text-[13px] leading-normal">
              {recipe.map(({ step, pending: isPending }, n) => (
                <li key={`${step.op}-${n}`} className={isPending ? "text-ink-accent" : undefined}>
                  <span className="block">{data.op_labels[step.op] ?? step.op}</span>
                  <span className="block break-all font-mono text-xs text-ink-dim">{argSummary(step)}</span>
                </li>
              ))}
            </ol>
          )}
          {pending.length > 0 && <p className="m-0 text-xs text-ink-accent">{t("recipe.pending")}</p>}
          <Tabs
            variant="dark"
            label={t("recipe.formats")}
            items={FORMATS.map((f) => ({
              value: f,
              label: f === "pandas" ? "pandas" : f.toUpperCase(),
              content: code ? (
                <CodeBlock code={code[f]} label={t("recipe.codeLabel", { format: f })} className="max-h-80 overflow-y-auto" />
              ) : (
                <SkeletonGroup lines={4} />
              ),
            }))}
          />
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="export-format" className="text-[13px] text-ink-dim">
              {t("recipe.exportFormat")}
            </label>
            <select
              id="export-format"
              value={format}
              onChange={(e) => setFormat(e.target.value as (typeof FORMATS)[number])}
              className="min-h-touch rounded-nav border border-ink-line bg-ink px-2 text-sm text-white"
            >
              {FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <Button variant="inverse" disabled={decided.length === 0} onClick={() => void exportCode(format)}>
            {t("recipe.export")}
          </Button>
          <p className="m-0 text-[13px] text-ink-dim">{t("recipe.replayNote")}</p>
        </section>
      </div>

      <section aria-labelledby="run-title" className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[22px]">
        <h2 id="run-title" className="m-0 text-lg font-semibold text-ink">
          {t("run.title")}
        </h2>
        <p className="m-0 text-[15px] text-muted">
          {t("run.summary", { done: resolved, total: issues.length, steps: decided.length })}
        </p>
        <div role="status" aria-live="polite" className="flex flex-col gap-2 text-[15px]">
          {(run.state === "saving" || run.state === "applying") && <span className="text-muted">{t(`run.${run.state}`)}</span>}
          {run.state === "error" && (
            <span className="flex flex-col text-flag-text">
              <strong>{run.problem.title}</strong>
              {run.problem.detail && <span>{run.problem.detail}</span>}
            </span>
          )}
          {run.state === "done" && (
            <dl className="m-0 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div className="flex flex-col">
                <dt className="text-muted">{t("run.quality")}</dt>
                <dd className="m-0 text-2xl font-semibold text-ink">
                  {t("run.qualityValue", { before: run.result.quality_before.score, after: run.result.quality_after.score })}
                </dd>
              </div>
              <div className="flex flex-col">
                <dt className="text-muted">{t("run.rows")}</dt>
                <dd className="m-0 text-2xl font-semibold text-ink">
                  {t("run.rowsValue", { before: formatNumber(locale, run.result.rows_before), after: formatNumber(locale, run.result.rows_after) })}
                </dd>
              </div>
              <div className="flex flex-col sm:col-span-2">
                <dt className="text-muted">{t("run.hash")}</dt>
                <dd className="m-0 break-all font-mono text-xs">{run.result.output_hash}</dd>
              </div>
            </dl>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => void saveAndApply()} disabled={decided.length === 0 || run.state === "saving" || run.state === "applying"}>
            {t("run.apply")}
          </Button>
          <ButtonLink href={`/datasets/${datasetRef}/sql`} variant={run.state === "done" ? "primary" : "secondary"}>
            {t("run.continue")}
          </ButtonLink>
        </div>
      </section>
    </div>
  );
}
