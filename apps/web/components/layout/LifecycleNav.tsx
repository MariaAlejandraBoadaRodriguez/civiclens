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
  { key: "dashboard", path: "/dashboard" },
] as const;

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
