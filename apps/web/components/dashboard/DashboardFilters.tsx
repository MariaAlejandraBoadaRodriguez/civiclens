"use client";

import { useEffect, useRef, useTransition } from "react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/routing";
import { CATEGORIES, PERIODS, type Category, type Period } from "@/lib/api-types";

export type ScopeOption = { value: string; label: string };

const selectClass =
  "min-h-touch min-w-[10rem] rounded-nav border border-line-strong bg-surface px-2.5 text-[15px] text-text";

/** Jurisdiction, period and category. Each change updates the URL (shareable, back button). */
export function DashboardFilters({
  scope,
  scopes,
  period,
  category,
}: {
  scope: string;
  scopes: ScopeOption[];
  period: Period;
  category: Category;
}) {
  const t = useTranslations("dashboard.filters");
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  // The latest choice of every filter. Read from a ref, not from the URL: a second change made
  // before the first navigation finished must not undo the first one.
  const values = useRef({ scope, period, category });
  useEffect(() => {
    values.current = { scope, period, category };
  }, [scope, period, category]);

  function update(key: "scope" | "period" | "category", value: string) {
    values.current = { ...values.current, [key]: value };
    const next = new URLSearchParams(values.current);
    startTransition(() => router.replace(`${pathname}?${next.toString()}`, { scroll: false }));
  }

  return (
    <form
      aria-label={t("label")}
      aria-busy={pending}
      onSubmit={(e) => e.preventDefault()}
      className="flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface px-4 py-3.5"
    >
      <label className="flex flex-col gap-1 text-[13px] text-muted">
        {t("jurisdiction")}
        <select id="filter-scope" name="scope" className={selectClass} value={scope} onChange={(e) => update("scope", e.target.value)}>
          {scopes.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-muted">
        {t("period")}
        <select id="filter-period" name="period" className={selectClass} value={period} onChange={(e) => update("period", e.target.value)}>
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {t(`periods.${p}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-muted">
        {t("category")}
        <select id="filter-category" name="category" className={selectClass} value={category} onChange={(e) => update("category", e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`categories.${c}`)}
            </option>
          ))}
        </select>
      </label>
      <span aria-live="polite" className="min-h-touch content-center text-[13px] text-muted">
        {pending ? t("updating") : ""}
      </span>
    </form>
  );
}
