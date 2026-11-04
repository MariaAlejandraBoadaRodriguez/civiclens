import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import type { DataColumn } from "@/lib/api-types";
import { formatNumber, formatPercent } from "@/lib/format";

/** Table `data`: every column of the cleaned file with its safe SQL name, kind and examples. */
export function DataColumns({ columns, rows }: { columns: DataColumn[]; rows: number }) {
  const t = useTranslations("sql.data");
  const locale = useLocale();
  return (
    <section aria-labelledby="data-table" className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[22px]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="data-table" className="m-0 text-lg font-semibold text-ink">
          {t.rich("title", { code: (chunks) => <code className="font-mono text-primary-dark">{chunks}</code> })}
        </h2>
        <p className="m-0 text-[13px] text-muted">
          {t("summary", { rows: formatNumber(locale, rows), columns: formatNumber(locale, columns.length) })}
        </p>
      </div>
      <p className="m-0 text-sm text-text">{t("hint")}</p>
      <DataTable
        caption={t("caption")}
        captionHidden
        minWidth={720}
        rows={columns}
        rowKey={(c) => c.name}
        columns={[
          { key: "name", header: t("name"), mono: true, cell: (c) => <span className="text-ink">{c.name}</span> },
          { key: "source", header: t("source"), cell: (c) => <span className="break-words">{c.source}</span> },
          {
            key: "kind",
            header: t("kind"),
            cell: (c) => (
              <span className="flex flex-wrap items-center gap-1.5">
                <Badge variant="format">{c.kind_label}</Badge>
                <span className="font-mono text-xs text-muted">{c.sql_type}</span>
              </span>
            ),
          },
          {
            key: "examples",
            header: t("examples"),
            mono: true,
            cell: (c) => <span className="text-[13px] text-text">{c.examples.join(" · ") || "—"}</span>,
          },
          {
            key: "nulls",
            header: t("missing"),
            align: "right",
            mono: true,
            cell: (c) => formatPercent(locale, rows ? c.nulls / rows : 0),
          },
        ]}
      />
    </section>
  );
}
