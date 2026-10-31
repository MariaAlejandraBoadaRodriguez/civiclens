import type { ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { IssueCardDemo } from "@/components/design/IssueCardDemo";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { KpiTile } from "@/components/ui/KpiTile";
import { ScoreBar } from "@/components/ui/ScoreBar";
import { Skeleton, SkeletonGroup } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { WakingUp } from "@/components/ui/WakingUp";
import {
  formatCompact,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
} from "@/lib/format";

export async function generateMetadata({ params: { locale } }: { params: { locale: string } }) {
  const t = await getTranslations({ locale, namespace: "design" });
  return { title: t("metaTitle") };
}

const SWATCHES = [
  { key: "ground", token: "--color-ground", hex: "#F4F6F8" },
  { key: "surface", token: "--color-surface", hex: "#FFFFFF" },
  { key: "ink", token: "--color-ink", hex: "#0F1B2D" },
  { key: "text", token: "--color-text", hex: "#1F2A37" },
  { key: "muted", token: "--color-muted", hex: "#4B5563" },
  { key: "line", token: "--color-line", hex: "#D7DDE4" },
  { key: "primary", token: "--color-primary", hex: "#1D4ED8" },
  { key: "primaryTint", token: "--color-primary-tint", hex: "#E8EEFC" },
  { key: "flag", token: "--color-flag", hex: "#B45309" },
  { key: "flagTint", token: "--color-flag-tint", hex: "#FDF1E4" },
  { key: "flagText", token: "--color-flag-text", hex: "#7C2D12" },
  { key: "success", token: "--color-success", hex: "#15803D" },
] as const;

type MappingRow = {
  source: string;
  type: "date" | "number" | "category" | "text";
  n?: number;
  canonical: string;
  confidence: number;
  nulls: number;
  options?: string[];
};

// Data values (source headers, canonical field names) are never translated.
const MAPPING: MappingRow[] = [
  { source: "fecha_de_firma", type: "date", canonical: "signed_date", confidence: 0.97, nulls: 0.004 },
  { source: "valor_del_contrato", type: "number", canonical: "amount_original", confidence: 0.95, nulls: 0.012 },
  { source: "nombre_entidad", type: "text", canonical: "entity_name", confidence: 0.93, nulls: 0 },
  { source: "proveedor_adjudicado", type: "text", canonical: "supplier_name", confidence: 0.88, nulls: 0.031 },
  {
    source: "modalidad_de_contratacion",
    type: "category",
    n: 11,
    canonical: "award_type",
    confidence: 0.71,
    nulls: 0.008,
    options: ["award_type", "category"],
  },
];

// Data-language codes as shown on dataset cards (data, not UI text).
const DATA_LANGUAGES = ["ES", "EN / FR", "FR"];

const joinDot = (...parts: string[]) => parts.join(" · ");

const SAMPLE_DATE = "2026-10-28T00:00:00Z";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h2 id={id} className="m-0 text-2xl font-semibold text-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

function MappingTable() {
  const t = useTranslations("design.table");
  const locale = useLocale();
  return (
    <DataTable
      caption={t("caption")}
      captionHidden
      minWidth={720}
      rows={MAPPING}
      rowKey={(r) => r.source}
      columns={[
        { key: "source", header: t("source"), cell: (r) => r.source, mono: true },
        { key: "type", header: t("type"), cell: (r) => t(`types.${r.type}`, { n: r.n ?? 0 }) },
        {
          key: "canonical",
          header: t("canonical"),
          mono: true,
          cell: (r) =>
            r.options ? (
              <>
                <label htmlFor={`ov-${r.source}`} className="sr-only">
                  {t("overrideLabel", { header: r.source })}
                </label>
                <select
                  id={`ov-${r.source}`}
                  defaultValue={r.canonical}
                  className="min-h-touch rounded-nav border border-flag bg-surface px-2 font-mono text-sm hover:border-flag-text"
                >
                  {r.options.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </>
            ) : (
              <span className="text-primary">{r.canonical}</span>
            ),
        },
        {
          key: "confidence",
          header: t("confidence"),
          mono: true,
          cell: (r) =>
            r.confidence < 0.8 ? (
              <span className="text-flag">{joinDot(formatNumber(locale, r.confidence, 2), t("check"))}</span>
            ) : (
              formatNumber(locale, r.confidence, 2)
            ),
        },
        { key: "nulls", header: t("nulls"), mono: true, cell: (r) => formatPercent(locale, r.nulls) },
      ]}
    />
  );
}

export default function DesignPage({ params: { locale } }: { params: { locale: string } }) {
  setRequestLocale(locale);
  const t = useTranslations("design");

  const formats = [
    { kind: t("formatting.number"), out: formatNumber(locale, 1234567.891, 2) },
    { kind: t("formatting.currency"), out: formatCurrency(locale, 1234.56, "CAD") },
    { kind: t("formatting.compact"), out: formatCompact(locale, 412_600_000, "CAD") },
    { kind: t("formatting.percent"), out: formatPercent(locale, 0.412) },
    { kind: t("formatting.dateLong"), out: formatDate(locale, SAMPLE_DATE) },
    { kind: t("formatting.dateShort"), out: formatDate(locale, SAMPLE_DATE, "short") },
  ];

  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-14 px-6 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <p className="m-0 font-mono text-[13px] uppercase tracking-wide text-primary">{t("eyebrow")}</p>
          <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
          <p className="m-0 max-w-2xl text-base text-muted">{t("intro")}</p>
        </div>
        <Badge variant="flag" className="px-2.5 py-1.5 text-[13px]">
          {t("sampleNote")}
        </Badge>
      </div>

      <Section id="colors" title={t("sections.colors")}>
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 p-0">
          {SWATCHES.map((s) => (
            <li key={s.key} className="flex flex-col overflow-hidden rounded-card border border-line bg-surface">
              <span aria-hidden="true" className="h-16 border-b border-line" style={{ background: `var(${s.token})` }} />
              <span className="flex flex-col gap-0.5 p-3">
                <span className="font-mono text-[13px] text-ink">{s.token}</span>
                <span className="font-mono text-xs text-muted">{s.hex}</span>
                <span className="text-[13px]">{t(`colors.${s.key}`)}</span>
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="typography" title={t("sections.typography")}>
        <Card as="div" className="gap-3">
          <p className="m-0 text-5xl font-semibold leading-tight text-ink">{t("type.display")}</p>
          <p className="m-0 text-[30px] font-semibold text-ink">{t("type.h1")}</p>
          <p className="m-0 text-lg font-semibold text-ink">{t("type.h2")}</p>
          <p className="m-0 text-base">{t("type.body")}</p>
          <p className="m-0 text-[13px] text-muted">{t("type.small")}</p>
          <p className="m-0 font-mono text-sm">{t("type.mono")}</p>
        </Card>
      </Section>

      <Section id="buttons" title={t("sections.buttons")}>
        <div className="flex flex-wrap items-center gap-3">
          <Button>{t("buttons.primary")}</Button>
          <Button variant="secondary">{t("buttons.secondary")}</Button>
          <Button variant="ghost">{t("buttons.ghost")}</Button>
          <Button variant="attention">{t("buttons.attention")}</Button>
          <ButtonLink href="/design">{t("buttons.link")}</ButtonLink>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled>{t("buttons.disabled")}</Button>
          <Button variant="secondary" disabled>
            {t("buttons.disabled")}
          </Button>
          <Button variant="ghost" disabled>
            {t("buttons.disabled")}
          </Button>
          <Button variant="attention" disabled>
            {t("buttons.disabled")}
          </Button>
        </div>
        <p className="m-0 text-sm text-muted">{t("buttons.stateNote")}</p>
      </Section>

      <Section id="badges" title={t("sections.badges")}>
        <div className="flex flex-wrap gap-2">
          {DATA_LANGUAGES.map((l) => (
            <Badge key={l} variant="language">
              {l}
            </Badge>
          ))}
          <Badge variant="format">{t("badges.csv")}</Badge>
          <Badge variant="flag">{t("badges.flag")}</Badge>
          <Badge variant="success">{t("badges.success")}</Badge>
          <Badge variant="info">{t("badges.info")}</Badge>
        </div>
      </Section>

      <Section id="cards" title={t("sections.cards")}>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          <Card title={t("card.title")} titleId="card-demo">
            {(
              [
                ["rowScore", "rowScoreValue"],
                ["rowRecipe", "rowRecipeValue"],
                ["rowSchema", "rowSchemaValue"],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3 border-b border-subtle pb-2.5 last:border-0">
                <span className="text-[15px]">{t(`card.${label}`)}</span>
                <span className="text-right font-mono text-[15px] text-ink">{t(`card.${value}`)}</span>
              </div>
            ))}
          </Card>
          <Alert
            variant="pii"
            title={t("pii.title")}
            titleId="pii-demo"
            actions={
              <>
                <Button variant="attention">{t("pii.mask")}</Button>
                <Button variant="attentionOutline">
                  {t("pii.review")}
                </Button>
              </>
            }
          >
            <p className="m-0">{t("pii.body")}</p>
            <ul className="m-0 flex flex-col gap-1 pl-[18px] font-mono text-sm">
              <li>{joinDot("documento_proveedor", t("pii.colId"))}</li>
              <li>{joinDot("email_contacto", t("pii.colEmail"))}</li>
            </ul>
          </Alert>
          <div className="flex flex-col gap-3">
            <Alert variant="warning">
              <p className="m-0">{t("warning")}</p>
            </Alert>
          </div>
        </div>
      </Section>

      <Section id="score" title={t("sections.score")}>
        <Card as="div" className="max-w-md">
          <div className="flex items-baseline gap-2" aria-label={`${t("score.label")}: 68 ${t("score.outOf")}`} role="img">
            <span className="text-[56px] font-semibold leading-none text-flag">{formatNumber(locale, 68)}</span>
            <span className="text-lg text-muted">{t("score.outOf")}</span>
          </div>
          <div className="flex flex-col gap-3">
            <ScoreBar label={t("score.completeness")} value={81} />
            <ScoreBar label={t("score.uniqueness")} value={94} />
            <ScoreBar label={t("score.validity")} value={62} />
            <ScoreBar label={t("score.consistency")} value={55} />
          </div>
        </Card>
      </Section>

      <Section id="kpis" title={t("sections.kpis")}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <KpiTile label={t("kpi.totalSpend")} value={formatCompact(locale, 412_600_000, "CAD")} note={t("kpi.totalSpendNote")} tone="positive" />
          <KpiTile label={t("kpi.contracts")} value={formatNumber(locale, 23_710)} note={t("kpi.contractsNote")} />
          <KpiTile
            label={t("kpi.avgValue")}
            value={formatCompact(locale, 17_400, "CAD")}
            note={t("kpi.avgValueNote", { median: formatCompact(locale, 4_100) })}
          />
          <KpiTile label={t("kpi.directAward")} value={formatPercent(locale, 0.41, 0)} note={t("kpi.directAwardNote")} tone="attention" />
          <KpiTile label={t("kpi.hhi")} value={formatNumber(locale, 0.031, 3)} note={t("kpi.hhiNote")} />
          <KpiTile label={t("kpi.quality")} value={formatNumber(locale, 81)} note={t("kpi.qualityNote", { before: 68 })} tone="positive" />
        </div>
      </Section>

      <Section id="issue" title={t("sections.issue")}>
        <IssueCardDemo />
      </Section>

      <Section id="table" title={t("sections.table")}>
        <Card as="div">
          <MappingTable />
        </Card>
      </Section>

      <Section id="tabs" title={t("sections.tabs")}>
        <Tabs
          label={t("tabs.label")}
          items={[
            { value: "redFlags", label: t("tabs.redFlags"), content: <p className="m-0 text-[15px]">{t("tabs.redFlagsBody")}</p> },
            { value: "forecast", label: t("tabs.forecast"), content: <p className="m-0 text-[15px]">{t("tabs.forecastBody")}</p> },
            { value: "classifier", label: t("tabs.classifier"), content: null, disabled: true },
            { value: "segments", label: t("tabs.segments"), content: null, disabled: true },
          ]}
        />
      </Section>

      <Section id="states" title={t("sections.states")}>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          <EmptyState
            title={t("empty.title")}
            body={t("empty.body")}
            action={<ButtonLink href="/">{t("empty.action")}</ButtonLink>}
          />
          <Card as="div">
            <Skeleton className="h-8 w-1/2" />
            <SkeletonGroup lines={4} />
          </Card>
          <WakingUp live={false} />
        </div>
      </Section>

      <Section id="formatting" title={t("sections.formatting")}>
        <Card as="div">
          <DataTable
            caption={t("formatting.caption")}
            minWidth={360}
            rows={formats}
            rowKey={(r) => r.kind}
            columns={[
              { key: "kind", header: t("formatting.kind"), cell: (r) => r.kind },
              { key: "out", header: t("formatting.output"), cell: (r) => r.out, mono: true, align: "right" },
            ]}
          />
        </Card>
      </Section>
    </main>
  );
}
