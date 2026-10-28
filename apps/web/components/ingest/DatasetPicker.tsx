import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { cn } from "@/lib/cn";

export const SAMPLE_SLUGS = ["secop_co", "contracts_ca", "contracts_qc"] as const;

/** Switch between the three sample datasets (mockup header chip "Dataset: …"). */
export function DatasetPicker({ current, path = "" }: { current: string | null; path?: string }) {
  const t = useTranslations("ingest.samples");
  return (
    <nav aria-label={t("label")} className="flex flex-wrap items-center gap-2">
      <span className="text-[13px] text-muted">{t("label")}</span>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {SAMPLE_SLUGS.map((slug) => (
          <li key={slug}>
            <Link
              href={`/datasets/${slug}${path}`}
              aria-current={current === slug ? "page" : undefined}
              className={cn(
                "inline-flex min-h-touch items-center rounded-nav border px-3 text-[13px] no-underline",
                current === slug
                  ? "border-ink bg-ink text-white hover:text-white"
                  : "border-line-strong bg-surface text-ink hover:border-ink hover:text-ink",
              )}
            >
              {t(slug)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
