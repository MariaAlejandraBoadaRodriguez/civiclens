import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { CleaningStudio } from "@/components/cleaning/CleaningStudio";
import { DatasetPicker } from "@/components/ingest/DatasetPicker";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { WakingUp } from "@/components/ui/WakingUp";
import { apiGet } from "@/lib/api";
import type { IssuesResponse } from "@/lib/api-types";

export const dynamic = "force-dynamic";

type Params = { params: { locale: string; id: string } };

export async function generateMetadata({ params: { locale } }: Params) {
  const t = await getTranslations({ locale, namespace: "clean" });
  return { title: t("metaTitle") };
}

export default async function CleanPage({ params: { locale, id } }: Params) {
  setRequestLocale(locale);
  const t = await getTranslations("clean");
  const result = await apiGet<IssuesResponse>(`/api/v1/datasets/${encodeURIComponent(id)}/issues`, locale, 60_000);

  const heading = (
    <div className="flex flex-col gap-1.5">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <p className="m-0 text-base text-muted">{t("subtitle")}</p>
    </div>
  );

  if (!result.ok) {
    const notReady = result.kind === "problem" && result.problem.code === "dataset.not_ready";
    return (
      <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
        {heading}
        <DatasetPicker current={id} path="/clean" />
        {result.kind === "unreachable" && (
          <>
            <WakingUp />
            <AutoRefresh />
          </>
        )}
        {notReady && (
          <Card as="div">
            <p className="m-0 text-[15px]">{t("notReady")}</p>
            <SkeletonGroup lines={5} />
            <AutoRefresh seconds={3} />
          </Card>
        )}
        {result.kind === "problem" && !notReady && (
          <EmptyState
            title={t("notFound.title")}
            body={t("notFound.body")}
            action={<ButtonLink href="/datasets/secop_co/clean">{t("notFound.action")}</ButtonLink>}
          />
        )}
      </main>
    );
  }

  const data = result.data;
  const ref = data.dataset.slug ?? data.dataset.id;
  const before = data.quality?.score;
  const after = data.quality_after?.score;
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        {heading}
        <Badge variant="info" className="px-2.5 py-1.5 font-mono text-xs">
          {after !== undefined && after !== null
            ? t("qualityChipAfter", { before: before ?? 0, after })
            : t("qualityChip", { before: before ?? 0 })}
        </Badge>
      </div>
      <DatasetPicker current={data.dataset.slug} path="/clean" />
      <p className="m-0 text-sm text-muted">{t("assumption")}</p>
      <Suspense fallback={<SkeletonGroup lines={8} />}>
        <CleaningStudio data={data} datasetRef={ref} />
      </Suspense>
    </main>
  );
}
