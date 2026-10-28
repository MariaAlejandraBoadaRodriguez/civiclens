"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";

/**
 * Override for a low-confidence header mapping. In this slice the choice is local; the
 * Cleaning Studio (slice 5b) saves it as a `rename_columns` recipe step.
 */
export function MappingSelect({
  header,
  value,
  options,
  labels,
}: {
  header: string;
  value: string | null;
  options: string[];
  labels: Record<string, string>;
}) {
  const t = useTranslations("ingest.mapping");
  const id = useId();
  const [current, setCurrent] = useState(value ?? "");
  const choices = Array.from(new Set([...(value ? [value] : []), ...options]));
  return (
    <>
      <label htmlFor={id} className="sr-only">
        {t("overrideLabel", { header })}
      </label>
      <select
        id={id}
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        className="min-h-touch max-w-[220px] rounded-nav border border-flag bg-surface px-2 font-mono text-sm hover:border-flag-text"
      >
        <option value="">{t("notMapped")}</option>
        {choices.map((field) => (
          <option key={field} value={field} title={labels[field]}>
            {field}
          </option>
        ))}
      </select>
    </>
  );
}
