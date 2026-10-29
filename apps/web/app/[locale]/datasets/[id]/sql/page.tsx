import { getTranslations, setRequestLocale } from "next-intl/server";
import { DatasetPicker, SAMPLE_SLUGS } from "@/components/ingest/DatasetPicker";
import { KpiCatalog } from "@/components/sql/KpiCatalog";
import { SqlLab } from "@/components/sql/SqlLab";
import { StarSchema } from "@/components/sql/StarSchema";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { WakingUp } from "@/components/ui/WakingUp";
import { Link } from "@/i18n/routing";
import { apiGet } from "@/lib/api";
import type { GuidedQueriesResponse, KpisResponse, StarSchemaResponse } from "@/lib/api-types";

export const dynamic = "force-dynamic";

type Params = { params: { locale: string; id: string } };

export async function generateMetadata({ params: { locale } }: Params) {
  const t = await getTranslations({ locale, namespace: "sql" });
  return { title: t("metaTitle") };
}

export default async function SqlPage({ params: { locale, id } }: Params) {
  setRequestLocale(locale);
  const t = await getTranslations("sql");
  const ref = encodeURIComponent(id);
  // The schema call builds the star schema on first use; KPIs reuse it.
  const schema = await apiGet<StarSchemaResponse>(`/api/v1/datasets/${ref}/schema`, locale, 60_000);
  const [guided, kpis] = await Promise.all([
    apiGet<GuidedQueriesResponse>("/api/v1/guided-queries", locale),
    schema.ok ? apiGet<KpisResponse>(`/api/v1/kpis/${ref}`, locale, 30_000) : Promise.resolve(null),
  ]);

  const heading = (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1.5">
        <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
        <p className="m-0 text-base text-muted">{t("subtitle")}</p>
      </div>
      <Badge variant="format" className="px-2.5 py-1.5 text-xs">
        {t("engineChip")}
      </Badge>
    </div>
  );

  if (!schema.ok || !guided.ok) {
    const failed = !schema.ok ? schema : guided.ok ? null : guided;
    const notReady = failed?.kind === "problem" && failed.problem.code === "dataset.not_ready";
    return (
      <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
        {heading}
        <DatasetPicker current={id} path="/sql" />
        {failed?.kind === "unreachable" && (
          <WakingUp />
        )}
        {notReady && (
          <Card as="div">
            <p className="m-0 text-[15px]">{t("notReady")}</p>
            <SkeletonGroup lines={5} />
            <AutoRefresh seconds={3} />
          </Card>
        )}
        {failed?.kind === "problem" && !notReady && (
          <EmptyState
            title={t("notFound.title")}
            body={t("notFound.body")}
            action={<ButtonLink href="/datasets/secop_co/sql">{t("notFound.action")}</ButtonLink>}
          />
        )}
      </main>
    );
  }

  const datasetRef = (SAMPLE_SLUGS as readonly string[]).includes(id) ? id : schema.data.dataset_id;
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      {heading}
      <DatasetPicker current={id} path="/sql" />
      {schema.data.origin === "recommended" && (
        <p className="m-0 text-sm text-muted">
          {t.rich("originRecommended", {
            link: (chunks) => (
              <Link href={`/datasets/${datasetRef}/clean`} className="underline underline-offset-2">
                {chunks}
              </Link>
            ),
          })}
        </p>
      )}
      <StarSchema tables={schema.data.tables} />
      <SqlLab datasetRef={datasetRef} guided={guided.data.items} guardrails={schema.data.guardrails} />
      {kpis?.ok && <KpiCatalog items={kpis.data.items} />}
      <div className="flex justify-end">
        <ButtonLink href={`/datasets/${datasetRef}/ml`}>{t("continue")}</ButtonLink>
      </div>
    </main>
  );
}

