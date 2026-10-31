import { getTranslations, setRequestLocale } from "next-intl/server";
import { DatasetPicker } from "@/components/ingest/DatasetPicker";
import { Dropzone } from "@/components/ingest/Dropzone";
import { MappingSelect } from "@/components/ingest/MappingSelect";
import { Alert } from "@/components/ui/Alert";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ScoreBar, SCORE_THRESHOLD } from "@/components/ui/ScoreBar";
import { SkeletonGroup } from "@/components/ui/Skeleton";
import { WakingUp } from "@/components/ui/WakingUp";
import { apiGet } from "@/lib/api";
import type { ColumnProfile, Profile } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { formatNumber, formatPercent } from "@/lib/format";

export const dynamic = "force-dynamic";

type Params = { params: { locale: string; id: string } };
type T = Awaited<ReturnType<typeof getTranslations<"ingest">>>;

export async function generateMetadata({ params: { locale } }: Params) {
  const t = await getTranslations({ locale, namespace: "ingest" });
  return { title: t("metaTitle") };
}

const DELIMITERS: Record<string, string> = { ",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe" };
const CANONICAL_ORDER = [
  "contract_id", "entity_id", "entity_name", "supplier_id", "supplier_name", "signed_date", "start_date",
  "end_date", "amount_original", "currency", "award_type", "n_bidders", "category_code", "description",
  "contract_type", "status", "region", "city",
];
const joinDot = (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(" · ");

/** Column worth a look before cleaning: low-confidence mapping, PII, or messy key field. */
function needsAttention(c: ColumnProfile): boolean {
  if (c.needs_check || c.pii_kind) return true;
  return Boolean(c.canonical_field) && (c.consistency < 0.99 || c.validity < 0.99 || c.null_ratio > 0.2);
}

function typeLabel(c: ColumnProfile, t: T): string {
  const base = t(`types.${c.inferred_type}`);
  const notes = Object.keys(c.notations ?? {});
  if (c.inferred_type === "number" || c.inferred_type === "integer") {
    if (notes.length > 1) return joinDot(base, t("detail.mixedNotation"));
    if (notes[0] === "comma") return joinDot(base, t("detail.commaDecimal"));
    return base;
  }
  if (c.inferred_type === "date" || c.inferred_type === "datetime") {
    return c.consistency < 0.99 ? joinDot(base, t("detail.mixedFormats")) : base;
  }
  if (c.inferred_type === "category") return joinDot(base, t("detail.values", { n: c.distinct }));
  return base;
}

function languageText(shares: Record<string, number>, locale: string, t: T): string {
  const entries = Object.entries(shares).filter(([, v]) => v >= 0.05);
  if (!entries.length) return t("languages.unknown");
  return entries.map(([lang, v]) => joinDot(t(`languages.${lang}`), formatPercent(locale, v, 0))).join(" / ");
}

function Unavailable({ kind, t, id }: { kind: "unreachable" | "notReady" | "notFound"; t: T; id: string }) {
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <DatasetPicker current={id} />
      {kind === "unreachable" && (
        <WakingUp />
      )}
      {kind === "notReady" && (
        <Card as="div">
          <p className="m-0 text-[15px]">{t("notReady")}</p>
          <SkeletonGroup lines={5} />
          <AutoRefresh seconds={3} />
        </Card>
      )}
      {kind === "notFound" && (
        <EmptyState
          title={t("notFound.title")}
          body={t("notFound.body")}
          action={<ButtonLink href="/datasets/secop_co">{t("notFound.action")}</ButtonLink>}
        />
      )}
    </main>
  );
}

export default async function IngestPage({ params: { locale, id } }: Params) {
  setRequestLocale(locale);
  const t = await getTranslations("ingest");
  const result = await apiGet<Profile>(`/api/v1/datasets/${encodeURIComponent(id)}/profile`, locale);
  if (!result.ok) {
    const kind =
      result.kind === "unreachable"
        ? "unreachable"
        : result.problem.code === "dataset.not_ready"
          ? "notReady"
          : "notFound";
    return <Unavailable kind={kind} t={t} id={id} />;
  }

  const p = result.data;
  const ref = p.dataset.slug ?? p.dataset.id;
  const rank = (c: ColumnProfile) =>
    c.canonical_field ? CANONICAL_ORDER.indexOf(c.canonical_field) : CANONICAL_ORDER.length;
  const columns = [...p.columns].sort((a, b) => rank(a) - rank(b));
  const attention = columns.filter(needsAttention).length;
  const scoreGood = p.quality.score >= SCORE_THRESHOLD;
  const delimiter = p.read.delimiter ? DELIMITERS[p.read.delimiter] : null;

  const meta: Array<[string, string]> = [
    [t("meta.format"), p.read.format.toUpperCase()],
    [t("meta.encoding"), p.read.encoding_label ?? t("meta.notApplicable")],
    [
      t("meta.delimiter"),
      delimiter ? joinDot(p.read.delimiter === "\t" ? "\\t" : p.read.delimiter, t(`delimiters.${delimiter}`)) : t("meta.notApplicable"),
    ],
    ...(p.read.sheet ? [[t("meta.sheet"), joinDot(p.read.sheet, t("meta.headerRow", { n: p.read.header_row + 1 }))] as [string, string]] : []),
    ...(p.read.records_path ? [[t("meta.records"), p.read.records_path] as [string, string]] : []),
    [t("meta.language"), languageText(p.data_lang, locale, t)],
    [t("meta.rowsColumns"), `${formatNumber(locale, p.rows)} × ${formatNumber(locale, p.columns_count)}`],
    [t("meta.storedAs"), t("meta.storedValue")],
  ];

  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
          <p className="m-0 text-base text-muted">{t("subtitle")}</p>
        </div>
        <Badge variant="info" className="px-2.5 py-1.5 font-mono text-xs">
          {t("datasetChip", { name: p.dataset.name })}
        </Badge>
      </div>
      <DatasetPicker current={p.dataset.slug} />

      <div className="flex flex-wrap gap-5">
        <Card title={t("source.title")} titleId="source" className="flex-[1_1_340px]">
          <Dropzone />
          <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {meta.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd className="m-0 break-words font-mono text-ink">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card title={t("score.title")} titleId="score" className="flex-[1_1_340px]">
          <p className="m-0 flex items-baseline gap-2">
            <span className={cn("text-[56px] font-semibold leading-none", scoreGood ? "text-primary" : "text-flag")}>
              {formatNumber(locale, p.quality.score)}
            </span>
            <span className="text-lg text-muted">{t("score.outOf")}</span>
            <span className="sr-only">{t("score.srLabel", { score: p.quality.score })}</span>
          </p>
          <div className="flex flex-col gap-3">
            {(["completeness", "uniqueness", "validity", "consistency"] as const).map((dim) => (
              <ScoreBar key={dim} label={t(`score.${dim}`)} value={p.quality[dim]} display={formatNumber(locale, p.quality[dim])} />
            ))}
          </div>
          <p className="m-0 text-[13px] text-muted">{t("score.explain")}</p>
        </Card>

        {p.pii.length > 0 ? (
          <Alert
            variant="pii"
            title={t("pii.title")}
            titleId="pii"
            className="flex-[1_1_300px]"
            actions={
              <>
                <ButtonLink
                  href={{ pathname: `/datasets/${ref}/clean`, query: { issue: "pii" } }}
                  variant="attention"
                  aria-describedby="pii-mask-note"
                >
                  {t("pii.mask")}
                </ButtonLink>
                <ButtonLink href={{ pathname: `/datasets/${ref}`, hash: "mapping" }} variant="attentionOutline">
                  {t("pii.review")}
                </ButtonLink>
              </>
            }
          >
            <p className="m-0">{t("pii.body", { count: p.pii.length })}</p>
            <ul className="m-0 flex flex-col gap-1 pl-[18px] font-mono text-sm">
              {p.pii.map((x) => (
                <li key={x.field}>{joinDot(x.field, x.label)}</li>
              ))}
            </ul>
            <p id="pii-mask-note" className="m-0 text-[13px]">
              {t("pii.maskNote")}
            </p>
          </Alert>
        ) : (
          <Card title={t("pii.noneTitle")} titleId="pii" className="flex-[1_1_300px]">
            <p className="m-0 text-[15px] text-muted">{t("pii.noneBody")}</p>
          </Card>
        )}
      </div>

      <Card
        title={t("mapping.title")}
        titleId="mapping"
        actions={<span className="text-sm text-muted">{t("mapping.subtitle")}</span>}
      >
        <DataTable
          caption={t("mapping.caption", { count: columns.length })}
          captionHidden
          minWidth={760}
          rows={columns}
          rowKey={(c) => c.source_header}
          columns={[
            { key: "source", header: t("mapping.source"), mono: true, cell: (c) => c.source_header },
            {
              key: "type",
              header: t("mapping.type"),
              cell: (c) => (
                <span className="flex flex-wrap items-center gap-1.5">
                  {typeLabel(c, t)}
                  {c.pii_kind && <Badge variant="flag">{c.pii_label}</Badge>}
                </span>
              ),
            },
            {
              key: "canonical",
              header: t("mapping.canonical"),
              cell: (c) =>
                c.needs_check ? (
                  <MappingSelect header={c.source_header} value={c.canonical_field} options={c.candidates} labels={c.candidate_labels} />
                ) : c.canonical_field ? (
                  <span className="flex flex-col">
                    <span className="font-mono text-primary">{c.canonical_field}</span>
                    <span className="text-[13px] text-muted">{c.label}</span>
                  </span>
                ) : (
                  <span className="text-muted">{t("mapping.unmapped")}</span>
                ),
            },
            {
              key: "confidence",
              header: t("mapping.confidence"),
              mono: true,
              cell: (c) =>
                c.canonical_field ? (
                  <span className={c.needs_check ? "text-flag" : undefined}>
                    {c.needs_check
                      ? joinDot(formatNumber(locale, c.mapping_confidence, 2), t("mapping.check"))
                      : formatNumber(locale, c.mapping_confidence, 2)}
                  </span>
                ) : (
                  <span className="text-muted">{t("mapping.none")}</span>
                ),
            },
            {
              key: "nulls",
              header: t("mapping.nulls"),
              mono: true,
              cell: (c) => {
                const coded = Object.keys(c.null_tokens ?? {}).filter(Boolean);
                return (
                  <span className="flex flex-col">
                    <span>{formatPercent(locale, c.null_ratio)}</span>
                    {coded.length > 0 && (
                      <span className="text-xs text-muted">{t("mapping.codedAs", { tokens: coded.slice(0, 3).join(", ") })}</span>
                    )}
                  </span>
                );
              },
            },
          ]}
        />
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-surface px-[22px] py-[18px]">
        <p className="m-0 text-[15px]">
          {t.rich("footer.summary", {
            count: attention,
            total: p.columns_count,
            strong: (chunks) => <strong className="font-semibold">{chunks}</strong>,
          })}
        </p>
        <ButtonLink href={`/datasets/${ref}/clean`}>{t("footer.continue")}</ButtonLink>
      </div>
    </main>
  );
}
