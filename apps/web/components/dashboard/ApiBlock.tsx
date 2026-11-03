import { useTranslations } from "next-intl";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { Link } from "@/i18n/routing";
import { PUBLIC_API_URL } from "@/lib/api";

/** "Automate this every month": the same pipeline through the public API. */
export function ApiBlock({ datasetRef }: { datasetRef: string }) {
  const t = useTranslations("dashboard.api");
  const api = PUBLIC_API_URL;
  // Code is never translated; only the comment lines follow the UI language.
  const code = [
    `# ${t("step1")}`,
    `curl -X POST ${api}/api/v1/datasets \\`,
    `  -H "X-API-Key: $CIVICLENS_KEY" -F "file=@contracts_2026_11.csv"`,
    ``,
    `# ${t("step2")}`,
    `curl -X POST ${api}/api/v1/datasets/$DATASET_ID/recipes/apply \\`,
    `  -H "X-API-Key: $CIVICLENS_KEY" -H "Content-Type: application/json" \\`,
    `  -d '{"recipe_id": "'$RECIPE_ID'"}'`,
    ``,
    `# ${t("step3")}`,
    `curl -H "X-API-Key: $CIVICLENS_KEY" "${api}/api/v1/dashboard?dataset_id=${datasetRef}&period=12m"`,
  ].join("\n");
  return (
    <section aria-labelledby="api-block" className="focus-on-dark flex flex-wrap gap-6 rounded-card bg-ink p-[22px] text-ink-text">
      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-2.5">
        <h2 id="api-block" className="m-0 text-lg font-semibold text-white">
          {t("title")}
        </h2>
        <p className="m-0 text-[15px] leading-relaxed">{t("body")}</p>
        <div className="flex flex-wrap gap-2.5">
          <a
            href={`${api}/docs`}
            className="inline-flex min-h-touch items-center rounded-control bg-surface px-4 text-[15px] font-medium text-ink no-underline hover:bg-subtle hover:text-ink"
          >
            {t("docs")}
          </a>
          <Link
            href="/admin"
            className="inline-flex min-h-touch items-center rounded-control border border-ink-line px-4 text-[15px] text-white no-underline hover:border-ink-text hover:text-white"
          >
            {t("key")}
          </Link>
        </div>
      </div>
      <CodeBlock code={code} label={t("codeLabel")} className="min-w-0 flex-[999_1_480px]" />
    </section>
  );
}
