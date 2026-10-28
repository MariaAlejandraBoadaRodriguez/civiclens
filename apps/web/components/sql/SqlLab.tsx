"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { PUBLIC_API_URL } from "@/lib/api";
import type { GuidedQuery, Guardrails, Problem, QueryCell, QueryResult } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatNumber, formatPercent } from "@/lib/format";

/** Rows rendered in the browser; the API returns up to 10,000 (the guardrail). */
const DISPLAY_ROWS = 200;
const FIRST_GUIDED = 6;
const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UBIGINT|UINTEGER|DOUBLE|FLOAT|REAL|DECIMAL)/i;
/** Result columns holding a 0–1 ratio, shown as a percentage (display only; the value is unchanged). */
const RATIO = /(share|_ratio|^hhi)$/;

type Run =
  | { state: "idle" }
  | { state: "running" }
  | { state: "done"; result: QueryResult }
  | { state: "error"; problem: Problem | null };

function cell(locale: string, value: QueryCell, column: string, numeric: boolean): string {
  if (value === null) return "—";
  if (typeof value === "number" && numeric) {
    if (RATIO.test(column) && Math.abs(value) <= 1) return formatPercent(locale, value);
    return formatNumber(locale, value, Number.isInteger(value) ? 0 : 2);
  }
  return String(value);
}

export function SqlLab({
  datasetRef,
  guided,
  guardrails,
}: {
  datasetRef: string;
  guided: GuidedQuery[];
  guardrails: Guardrails;
}) {
  const t = useTranslations("sql");
  const locale = useLocale();
  const [selected, setSelected] = useState<string>(guided[0]?.query_id ?? "");
  const [sql, setSql] = useState<string>(guided[0]?.sql ?? "");
  const [showAll, setShowAll] = useState(false);
  const [run, setRun] = useState<Run>({ state: "idle" });
  const controller = useRef<AbortController | null>(null);

  const query = guided.find((q) => q.query_id === selected);
  const edited = query !== undefined && sql.trim() !== query.sql.trim();
  const visible = showAll ? guided : guided.slice(0, FIRST_GUIDED);

  const execute = useCallback(
    async (text: string) => {
      controller.current?.abort();
      const current = new AbortController();
      controller.current = current;
      setRun({ state: "running" });
      try {
        const res = await fetch(`${PUBLIC_API_URL}/api/v1/query`, {
          method: "POST",
          headers: { "Accept-Language": locale, "Content-Type": "application/json" },
          body: JSON.stringify({ dataset_id: datasetRef, sql: text }),
          signal: current.signal,
        });
        const body = await res.json().catch(() => null);
        if (current.signal.aborted) return;
        if (res.ok) setRun({ state: "done", result: body as QueryResult });
        else setRun({ state: "error", problem: body && "code" in body ? (body as Problem) : null });
      } catch {
        if (!current.signal.aborted) setRun({ state: "error", problem: null });
      }
    },
    [datasetRef, locale],
  );

  useEffect(() => {
    if (guided[0]) void execute(guided[0].sql);
    return () => controller.current?.abort();
  }, [execute, guided]);

  function choose(q: GuidedQuery) {
    setSelected(q.query_id);
    setSql(q.sql);
    void execute(q.sql);
  }

  const result = run.state === "done" ? run.result : null;
  const columns = useMemo<Column<QueryCell[]>[]>(
    () =>
      (result?.columns ?? []).map((c, i) => {
        const numeric = NUMERIC.test(c.type);
        return {
          key: `${i}-${c.name}`,
          header: c.name,
          align: numeric ? "right" : "left",
          mono: true,
          cell: (row) => cell(locale, row[i], c.name, numeric),
        };
      }),
    [result, locale],
  );

  return (
    <div className="flex flex-wrap items-start gap-5">
      <nav
        aria-labelledby="guided"
        className="flex min-w-0 flex-[1_1_260px] flex-col gap-1 rounded-card border border-line bg-surface p-3"
      >
        <p id="guided" className="mx-2 mb-2 mt-1.5 text-[13px] font-medium text-muted">
          {t("guided.title", { n: guided.length })}
        </p>
        <ul id="guided-list" className="m-0 flex list-none flex-col gap-1 p-0">
          {visible.map((q) => {
            const active = q.query_id === selected;
            return (
              <li key={q.query_id}>
                <button
                  type="button"
                  onClick={() => choose(q)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "min-h-touch w-full rounded-control p-2.5 text-left text-sm",
                    active ? "bg-primary-tint font-medium text-primary-dark" : "text-text hover:bg-ground",
                  )}
                >
                  {q.question}
                </button>
              </li>
            );
          })}
        </ul>
        {guided.length > FIRST_GUIDED && (
          <button
            type="button"
            aria-expanded={showAll}
            aria-controls="guided-list"
            onClick={() => setShowAll((v) => !v)}
            className="min-h-touch rounded-control p-2.5 text-left text-sm text-primary underline-offset-4 hover:text-primary-dark hover:underline"
          >
            {showAll ? t("guided.showFewer") : t("guided.showAll", { n: guided.length })}
          </button>
        )}
      </nav>

      <section aria-labelledby="editor" className="flex min-w-0 flex-[999_1_560px] flex-col gap-4">
        <div className="focus-on-dark overflow-hidden rounded-card bg-ink">
          <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-ink-line px-3.5 py-2.5">
            <h2 id="editor" className="m-0 text-sm font-medium text-white">
              {t("editor.title")}
            </h2>
            <span id="guardrails" className="text-xs text-ink-text">
              {t("editor.guardrails", { seconds: guardrails.timeout_s, rows: guardrails.max_rows })}
            </span>
            <Button
              onClick={() => void execute(sql)}
              disabled={run.state === "running" || !sql.trim()}
              aria-keyshortcuts="Control+Enter Meta+Enter"
            >
              {run.state === "running" ? t("editor.running") : t("editor.run")}
            </Button>
          </div>
          <label htmlFor="sql-editor" className="sr-only">
            {t("editor.label")}
          </label>
          <textarea
            id="sql-editor"
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                void execute(sql);
              }
            }}
            aria-describedby="guardrails editor-hint"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            rows={Math.min(18, Math.max(8, sql.split("\n").length + 1))}
            className="block w-full resize-y border-0 bg-ink p-4 font-mono text-[13px] leading-[1.7] text-code-text outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ink-accent"
          />
          <p id="editor-hint" className="m-0 border-t border-ink-line px-3.5 py-2 text-xs text-ink-text">
            {t("editor.hint")}
          </p>
        </div>

        <div
          id="query-results"
          aria-live="polite"
          aria-busy={run.state === "running"}
          className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[18px]"
        >
          {run.state === "error" && (
            <Alert variant="warning" title={run.problem?.title ?? t("results.unreachable")} titleId="query-error">
              {run.problem?.detail && <p className="m-0">{run.problem.detail}</p>}
            </Alert>
          )}
          {run.state === "running" && <p className="m-0 text-sm text-muted">{t("results.running")}</p>}
          {result && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="m-0 text-sm font-medium text-ink">
                  {t("results.title", { count: result.row_count, ms: result.elapsed_ms })}
                </h3>
                {result.truncated && (
                  <Badge variant="flag">{t("results.truncated", { rows: guardrails.max_rows })}</Badge>
                )}
              </div>
              {result.row_count === 0 ? (
                <p className="m-0 text-sm text-muted">{t("results.empty")}</p>
              ) : (
                <DataTable
                  caption={t("results.caption")}
                  captionHidden
                  columns={columns}
                  rows={result.rows.slice(0, DISPLAY_ROWS)}
                  rowKey={(_, i) => String(i)}
                  minWidth={480}
                />
              )}
              {result.row_count > DISPLAY_ROWS && (
                <p className="m-0 text-[13px] text-muted">
                  {t("results.displayCap", { shown: DISPLAY_ROWS, count: result.row_count })}
                </p>
              )}
            </>
          )}
          {query && (
            <div className="flex flex-col gap-2 rounded-control bg-ground px-3.5 py-3 text-sm leading-relaxed">
              <p className="m-0">
                <strong className="font-semibold">{t("teaches")}</strong> {query.explanation}
              </p>
              <ul aria-label={t("concepts.label")} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {query.concepts.map((c) => (
                  <li key={c}>
                    <Badge variant="format">{t(`concepts.${c}`)}</Badge>
                  </li>
                ))}
              </ul>
              {edited && <p className="m-0 text-[13px] text-muted">{t("edited")}</p>}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
