import { getTranslations, setRequestLocale } from "next-intl/server";
import { ApiBlock } from "@/components/dashboard/ApiBlock";
import { DashboardFilters, type ScopeOption } from "@/components/dashboard/DashboardFilters";
import { GenericDashboard } from "@/components/dashboard/GenericDashboard";
import { JurisdictionBars } from "@/components/dashboard/JurisdictionBars";
import { kpiTile } from "@/components/dashboard/kpiTiles";
import { MonthlyChart } from "@/components/dashboard/MonthlyChart";
import { DatasetPicker, SAMPLE_SLUGS } from "@/components/ingest/DatasetPicker";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink, buttonClass } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { KpiTile } from "@/components/ui/KpiTile";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { WakingUp } from "@/components/ui/WakingUp";
import { PUBLIC_API_URL, apiGet } from "@/lib/api";
import { ROUTE_UNAVAILABLE } from "@/lib/routeUnavailable";
import {
  CATEGORIES,
  PERIODS,
  type Category,
  type Dashboard,
  type Dataset,
  type Overview,
  type Period,
} from "@/lib/api-types";

export const dynamic = "force-dynamic";

type Props = {
  params: { locale: string; id: string };
  searchParams: { scope?: string; period?: string; category?: string };
};

export async function generateMetadata({ params: { locale } }: Props) {
  const t = await getTranslations({ locale, namespace: "dashboard" });
  return { title: t("metaTitle") };
}

const isSample = (ref: string) => (SAMPLE_SLUGS as readonly string[]).includes(ref);
const query = (refs: readonly string[], period: Period, category: Category) =>
  `/api/v1/dashboard?${refs.map((r) => `dataset_id=${encodeURIComponent(r)}`).join("&")}&period=${period}&category=${category}`;

export default async function DashboardPage({ params: { locale, id }, searchParams }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("dashboard");
  const tc = await getTranslations("common.apiError");
  const period: Period = (PERIODS as readonly string[]).includes(searchParams.period ?? "") ? (searchParams.period as Period) : "all";
  const category: Category = (CATEGORIES as readonly string[]).includes(searchParams.category ?? "")
    ? (searchParams.category as Category)
    : "all";

  const dataset = await apiGet<Dataset>(`/api/v1/datasets/${encodeURIComponent(id)}`, locale);
  const heading = (
    <div className="flex min-w-0 flex-col gap-1.5">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <p className="m-0 text-base text-muted">{t("subtitle")}</p>
    </div>
  );
  if (!dataset.ok) {
    return (
      <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
        {heading}
        <DatasetPicker current={id} path="/dashboard" />
        {dataset.kind === "unreachable" ? (
          <WakingUp />
        ) : (
          <EmptyState
            title={t("notFound.title")}
            body={t("notFound.body")}
            action={<ButtonLink href="/datasets/secop_co/dashboard">{t("notFound.action")}</ButtonLink>}
          />
        )}
      </main>
    );
  }

  const ref = isSample(id) ? id : dataset.data.id;
  const scopes: ScopeOption[] = [
    { value: "all", label: t("scopes.all") },
    ...SAMPLE_SLUGS.map((s) => ({ value: s, label: t(`scopes.${s}`) })),
    ...(isSample(ref) ? [] : [{ value: ref, label: t("scopes.upload", { name: dataset.data.name }) }]),
  ];
  const scope = scopes.some((s) => s.value === searchParams.scope) ? (searchParams.scope as string) : ref;
  const selected = scope === "all" ? SAMPLE_SLUGS : [scope];
  const compared = isSample(ref) ? SAMPLE_SLUGS : [...SAMPLE_SLUGS, ref];
  const [main, comparison] = await Promise.all([
    apiGet<Dashboard>(query(selected, period, category), locale, 60_000),
    apiGet<Dashboard>(query(compared, period, category), locale, 60_000),
  ]);

  const notReady = !main.ok && main.kind === "problem" && main.problem.code === "dataset.not_ready";
  // Not procurement data: the dashboard for any table (KPIs, findings, chart builder).
  const generic = !main.ok && main.kind === "problem" && main.problem.code === "domain.procurement_only";
  const overview = generic
    ? await apiGet<Overview>(`/api/v1/datasets/${encodeURIComponent(ref)}/overview`, locale, 60_000)
    : null;
  const reportUrl = `${PUBLIC_API_URL}/api/v1/reports/${encodeURIComponent(ref)}?lang=${locale}`;
  const exportUrl = `${PUBLIC_API_URL}/api/v1/datasets/${encodeURIComponent(ref)}/export?format=parquet`;
  const current = main.ok ? main.data.by_jurisdiction.find((j) => j.dataset_id === dataset.data.id) : undefined;

  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        {heading}
        <div className="flex flex-wrap gap-2.5">
          <a href={reportUrl} target="_blank" rel="noopener" className={buttonClass("primary")}>
            {t("actions.report")}
            <span className="sr-only">{t("actions.newTab")}</span>
          </a>
          <a href={`${reportUrl}&format=pdf`} target="_blank" rel="noopener" className={buttonClass("secondary")}>
            {t("actions.pdf")}
            <span className="sr-only">{t("actions.newTab")}</span>
          </a>
          <a href={exportUrl} download className={buttonClass("secondary")}>
            {t("actions.export")}
          </a>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <DatasetPicker current={id} path="/dashboard" />
        {current && (
          <Badge variant={current.origin === "clean" ? "success" : "info"}>
            {current.origin === "clean" ? t("origin.clean") : t("origin.recommended")}
          </Badge>
        )}
      </div>
      {!generic && <DashboardFilters scope={scope} scopes={scopes} period={period} category={category} />}

      {!main.ok && main.kind === "unreachable" && <WakingUp />}
      {notReady && (
        <Card as="div">
          <p className="m-0 text-[15px]">{t("notReady")}</p>
          <SkeletonGroup lines={5} />
          <AutoRefresh seconds={3} />
        </Card>
      )}
      {overview?.ok && <GenericDashboard overview={overview.data} datasetRef={ref} />}
      {overview && !overview.ok && overview.kind === "problem" && (
        <EmptyState title={overview.problem.title} body={overview.problem.detail} />
      )}
      {overview && !overview.ok && overview.kind === "unreachable" && <WakingUp />}
      {!main.ok && main.kind === "problem" && !notReady && !generic && (
        main.problem.code === ROUTE_UNAVAILABLE ? (
          <EmptyState title={tc("routeTitle")} body={tc("routeBody")} />
        ) : (
          <EmptyState title={main.problem.title} body={main.problem.detail} />
        )
      )}

      {main.ok && (
        <>
          <section aria-labelledby="kpis-heading" className="flex flex-col gap-3">
            <h2 id="kpis-heading" className="sr-only">
              {t("kpisHeading")}
            </h2>
            <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
              {main.data.kpis.map((k) => {
                const tile = kpiTile(k, locale, (key, values) => t(key, values));
                return (
                  <li key={tile.id} title={tile.title} data-testid="kpi-tile">
                    <KpiTile label={tile.label} value={tile.value} note={tile.note} tone={tile.tone} />
                  </li>
                );
              })}
            </ul>
            <p className="m-0 text-[13px] text-muted">{t("currencyNote")}</p>
          </section>

          <div className="flex flex-wrap items-start gap-5">
            <Card title={t("monthly.title")} titleId="monthly" className="flex-[999_1_560px]">
              {main.data.monthly.length > 0 ? (
                <MonthlyChart monthly={main.data.monthly} peak={main.data.peak} />
              ) : null}
              <p className="m-0 text-sm" data-testid="finding">
                <strong className="font-semibold">{t("monthly.finding")}</strong> {main.data.finding}
              </p>
            </Card>
            <Card title={t("jurisdictions.title")} titleId="jurisdictions" className="flex-[1_1_320px]">
              <p className="m-0 text-[13px] text-muted" data-testid="jurisdiction-filters">
                {t("jurisdictions.filtered", {
                  period: t(`filters.periods.${period}`),
                  category: t(`filters.categories.${category}`),
                })}
              </p>
              {comparison.ok ? (
                <JurisdictionBars
                  items={comparison.data.by_jurisdiction}
                  selected={main.data.by_jurisdiction.map((j) => j.dataset_id)}
                />
              ) : (
                <p className="m-0 text-sm">{t("jurisdictions.unavailable")}</p>
              )}
              <div className="flex flex-col gap-1.5 rounded-control bg-ground p-3 text-[13px] leading-normal text-text">
                <h3 className="m-0 text-[13px] font-semibold">{t("notes.title")}</h3>
                <ul className="m-0 flex list-disc flex-col gap-1 pl-4">
                  {(comparison.ok ? comparison.data.notes : main.data.notes).map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
            </Card>
          </div>
        </>
      )}
      <ApiBlock datasetRef={ref} />
    </main>
  );
}
