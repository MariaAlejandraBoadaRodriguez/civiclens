import { getTranslations, setRequestLocale } from "next-intl/server";
import { DatasetPicker, SAMPLE_SLUGS } from "@/components/ingest/DatasetPicker";
import { GenericMlLab } from "@/components/ml/GenericMlLab";
import { MlLab } from "@/components/ml/MlLab";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { WakingUp } from "@/components/ui/WakingUp";
import { apiGet } from "@/lib/api";
import type {
  AnomaliesResult,
  Dataset,
  ForecastResult,
  RedFlagResult,
  SegmentsResult,
  StarSchemaResponse,
  TargetModelResult,
} from "@/lib/api-types";

export const dynamic = "force-dynamic";

type Params = { params: { locale: string; id: string } };

export async function generateMetadata({ params: { locale } }: Params) {
  const t = await getTranslations({ locale, namespace: "ml" });
  return { title: t("metaTitle") };
}

export default async function MlPage({ params: { locale, id } }: Params) {
  setRequestLocale(locale);
  const t = await getTranslations("ml");
  const ref = encodeURIComponent(id);
  const dataset = await apiGet<Dataset>(`/api/v1/datasets/${ref}`, locale);
  const [redFlags, forecast] = await Promise.all([
    apiGet<RedFlagResult>(`/api/v1/models/red_flags/latest?dataset_id=${ref}`, locale),
    apiGet<ForecastResult>(`/api/v1/models/forecast/latest?dataset_id=${ref}`, locale),
  ]);

  const heading = (
    <div className="flex flex-col gap-1.5">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <p className="m-0 text-base text-muted">{t("subtitle")}</p>
    </div>
  );
  // "not run yet" is normal: the lab trains the model in the browser session.
  const notReady =
    !redFlags.ok && redFlags.kind === "problem" && redFlags.problem.code === "dataset.not_ready";

  // Red flags need procurement data; any other table gets the generic models.
  const generic =
    !redFlags.ok && redFlags.kind === "problem" && redFlags.problem.code === "domain.procurement_only";

  if (!dataset.ok || notReady) {
    return (
      <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
        {heading}
        <DatasetPicker current={id} path="/ml" />
        {!dataset.ok && dataset.kind === "unreachable" && (
          <WakingUp />
        )}
        {notReady && (
          <Card as="div">
            <p className="m-0 text-[15px]">{t("notReady")}</p>
            <SkeletonGroup lines={5} />
            <AutoRefresh seconds={3} />
          </Card>
        )}
        {!dataset.ok && dataset.kind === "problem" && (
          <EmptyState
            title={t("notFound.title")}
            body={t("notFound.body")}
            action={<ButtonLink href="/datasets/secop_co/ml">{t("notFound.action")}</ButtonLink>}
          />
        )}
      </main>
    );
  }

  const datasetRef = (SAMPLE_SLUGS as readonly string[]).includes(id) ? id : dataset.data.id;
  if (generic) {
    const latest = <T,>(model: string) =>
      apiGet<T>(`/api/v1/models/${model}/latest?dataset_id=${ref}`, locale).then((r) => (r.ok ? r.data : null));
    const [schema, target, anomalies, segments] = await Promise.all([
      apiGet<StarSchemaResponse>(`/api/v1/datasets/${ref}/schema`, locale, 30_000),
      latest<TargetModelResult>("target_model"),
      latest<AnomaliesResult>("anomalies"),
      latest<SegmentsResult>("segments"),
    ]);
    return (
      <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
        {heading}
        <DatasetPicker current={id} path="/ml" />
        <GenericMlLab
          datasetRef={datasetRef}
          columns={schema.ok ? schema.data.data_columns : []}
          initial={{ target, anomalies, segments, forecast: forecast.ok ? forecast.data : null }}
        />
        <div className="flex justify-end">
          <ButtonLink href={`/datasets/${encodeURIComponent(id)}/dashboard`}>{t("continue")}</ButtonLink>
        </div>
      </main>
    );
  }
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      {heading}
      <DatasetPicker current={id} path="/ml" />
      <MlLab
        datasetRef={datasetRef}
        redFlags={redFlags.ok ? redFlags.data : null}
        forecast={forecast.ok ? forecast.data : null}
      />
      <div className="flex justify-end">
        <ButtonLink href={`/datasets/${encodeURIComponent(id)}/dashboard`}>{t("continue")}</ButtonLink>
      </div>
    </main>
  );
}
