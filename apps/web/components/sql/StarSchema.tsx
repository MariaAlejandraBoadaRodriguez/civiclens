import { useTranslations } from "next-intl";
import type { StarTable } from "@/lib/api-types";
import { cn } from "@/lib/cn";

/** Grid position of each table: fact in the centre, dimensions around it (mockup layout). */
const LAYOUT: Record<string, string> = {
  dim_entity: "md:col-start-1 md:row-start-1",
  dim_date: "md:col-start-2 md:row-start-1",
  dim_supplier: "md:col-start-3 md:row-start-1",
  fact_contract: "md:col-start-2 md:row-start-2",
  dim_category: "md:col-start-1 md:row-start-2",
  dim_currency: "md:col-start-3 md:row-start-2",
};

/** Columns shown per table in the diagram (table and column names are never translated). */
const SHOWN: Record<string, string[]> = {
  fact_contract: [
    "contract_id",
    "entity_id",
    "supplier_id",
    "date_id",
    "category_id",
    "amount_cad",
    "award_type",
    "n_bidders",
  ],
  dim_entity: ["entity_id", "entity_name", "region"],
  dim_date: ["date_id", "month", "fiscal_year"],
  dim_supplier: ["supplier_id", "supplier_name", "first_seen"],
  dim_category: ["category_id", "label_en", "label_es"],
  dim_currency: ["currency", "cad_per_unit", "fx_month"],
};

export function StarSchema({ tables }: { tables: StarTable[] }) {
  const t = useTranslations("sql.schema");
  const ordered = Object.keys(LAYOUT)
    .map((name) => tables.find((table) => table.name === name))
    .filter((table): table is StarTable => Boolean(table));
  return (
    <section aria-labelledby="schema" className="flex flex-col gap-4 rounded-card border border-line bg-surface p-[22px]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="schema" className="m-0 text-lg font-semibold text-ink">
          {t("title")}
        </h2>
        <p className="m-0 text-[13px] text-muted">{t("hint")}</p>
      </div>
      <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
        {ordered.map((table) => {
          const fact = table.role === "fact";
          const available = new Set(table.columns.map((c) => c.name));
          const shown = (SHOWN[table.name] ?? []).filter((c) => available.has(c));
          return (
            <li
              key={table.name}
              className={cn(
                "flex flex-col gap-1 rounded-control p-3 font-mono text-[13px]",
                LAYOUT[table.name],
                fact ? "order-first border-2 border-primary bg-primary-soft md:order-none" : "border border-line",
              )}
            >
              <span className="flex flex-wrap items-baseline justify-between gap-2">
                <span className={cn("font-medium", fact ? "text-primary-dark" : "text-ink")}>{table.name}</span>
                <span className="font-sans text-xs text-muted">{t("rows", { count: table.rows })}</span>
              </span>
              <span className={fact ? "text-text" : "text-muted"}>{shown.join(" · ")}</span>
              <span className="sr-only">{t("columnsCount", { n: table.columns.length })}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
