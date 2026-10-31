"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/routing";
import { cn } from "@/lib/cn";

/** Dataset used by the lifecycle links when the current page is not about a dataset. */
export const DEFAULT_DATASET = "secop_co";

export const LIFECYCLE_STEPS = [
  { key: "ingest", path: "" },
  { key: "clean", path: "/clean" },
  { key: "sql", path: "/sql" },
  { key: "ml", path: "/ml" },
  { key: "dashboard", path: "/dashboard", soon: true }, // Phase 6
] as const satisfies readonly { key: string; path: string; soon?: boolean }[];

export function LifecycleNav({ datasetId }: { datasetId?: string }) {
  const t = useTranslations("nav");
  const params = useParams<{ id?: string }>();
  const current = datasetId ?? params?.id ?? DEFAULT_DATASET;
  const pathname = usePathname();

  return (
    <nav aria-label={t("lifecycle")} className="focus-on-dark flex-auto">
      <ol className="m-0 flex list-none flex-wrap gap-1 p-0">
        {LIFECYCLE_STEPS.map((step, i) => {
          const href = `/datasets/${current}${step.path}`;
          const active = pathname === href;
          if ("soon" in step && step.soon) {
            // Not built yet: shown disabled, never as a link to a missing page.
            return (
              <li key={step.key}>
                <span
                  aria-disabled="true"
                  title={t("comingSoon")}
                  className="inline-flex min-h-touch cursor-not-allowed items-center gap-1.5 rounded-nav px-3 text-sm text-ink-dim"
                >
                  <span aria-hidden="true">{i + 1}</span>
                  <span className="sr-only">{t("step", { n: i + 1 })}</span>
                  {t(step.key)}
                  <span className="rounded-chip border border-ink-line px-1.5 text-[11px] leading-5">{t("comingSoon")}</span>
                </span>
              </li>
            );
          }
          return (
            <li key={step.key}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-touch items-center gap-1.5 rounded-nav px-3 text-sm no-underline",
                  active ? "bg-ink-raised text-white hover:text-white" : "text-ink-text hover:bg-ink-raised hover:text-white",
                )}
              >
                <span aria-hidden="true">{i + 1}</span>
                <span className="sr-only">{t("step", { n: i + 1 })}</span>
                {t(step.key)}
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
