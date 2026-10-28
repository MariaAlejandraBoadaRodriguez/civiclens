"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { BeforeAfter } from "@/components/ui/BeforeAfter";
import { Button } from "@/components/ui/Button";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { IssueCard } from "@/components/ui/IssueCard";
import { OptionRadio } from "@/components/ui/OptionRadio";
import { Tabs } from "@/components/ui/Tabs";
import { formatCompact, formatCurrency, formatNumber } from "@/lib/format";

// Illustrative sample (mockup screen 2). Real values come from the API in Phase 5b.
const BEFORE = [
  { amount: 1_250_000_000, currency: "COP" },
  { amount: 48_500, currency: "USD" },
  { amount: 12_300, currency: "CAD" },
];
const TO_CAD: Record<string, number> = { COP: 0.000323, USD: 1.37, CAD: 1 };
const TOTAL_CAD = 412_600_000;
const OPTIONS = ["CAD", "COP", "USD", "KEEP"] as const;
type Option = (typeof OPTIONS)[number];

const STEPS = ['drop_duplicates(keep="first")', 'parse_numbers(locale="es_CO")'];

const convertStep = (target: string) => `convert_currency(to="${target}")`;

function code(target: string) {
  return {
    pandas: `df = df.drop_duplicates()\ndf["amount"] = parse_es(df["valor"])\ndf = to_currency(df, "${target}",\n                 fx=fx_by_date)`,
    sql: `SELECT DISTINCT *,\n  amount_original * fx.rate AS amount_${target.toLowerCase()}\nFROM staged s\nJOIN fx_rates fx\n  ON fx.date = s.signed_date\n AND fx.from_ccy = s.currency\n AND fx.to_ccy = '${target}'`,
    json: `{\n  "version": 1,\n  "steps": [\n    {"op": "drop_duplicates", "keep": "first"},\n    {"op": "parse_numbers", "locale": "es_CO"},\n    {"op": "convert_currency", "to": "${target}"}\n  ]\n}`,
  };
}

export function IssueCardDemo() {
  const t = useTranslations("design.issue");
  const locale = useLocale();
  const [picked, setPicked] = useState<Option>("CAD");
  const target = picked === "KEEP" ? "CAD" : picked;
  const rate = (from: string) => TO_CAD[from] / TO_CAD[target];

  const after = BEFORE.map((b) => formatCurrency(locale, b.amount * rate(b.currency), target));
  const total = formatCompact(locale, TOTAL_CAD / TO_CAD[target], target);
  const snippets = code(target);

  return (
    <div className="flex flex-wrap items-start gap-5">
      <div className="min-w-0 flex-[999_1_520px]">
        <IssueCard
          id="demo-issue"
          eyebrow={t("eyebrow")}
          title={t("title")}
          found={t("found", {
            cop: formatNumber(locale, 24_312),
            usd: formatNumber(locale, 412),
            cad: formatNumber(locale, 88),
          })}
          why={t("why")}
          options={
            <OptionRadio
              legend={t("legend")}
              value={picked}
              onValueChange={(v) => setPicked(v as Option)}
              options={OPTIONS.map((o) => ({
                value: o,
                label: t(`options.${o}`),
                hint: t(`options.${o}Hint`),
              }))}
            />
          }
          preview={
            <BeforeAfter
              before={BEFORE.map((b) => formatCurrency(locale, b.amount, b.currency))}
              after={after}
              afterLabel={picked === "KEEP" ? t("newColumn", { currency: "CAD" }) : target}
            />
          }
          impact={{ label: t("impactLabel"), before: t("impactBefore"), after: total, note: t("impactNote") }}
          actions={
            <>
              <Button>{t("apply")}</Button>
              <Button variant="secondary">{t("skip")}</Button>
              <Button variant="ghost">{t("learnMore")}</Button>
            </>
          }
        />
      </div>
      <section
        aria-labelledby="demo-recipe"
        className="focus-on-dark flex min-w-0 flex-[1_1_280px] flex-col gap-3.5 rounded-card bg-ink p-5 text-code-text"
      >
        <h3 id="demo-recipe" className="m-0 text-base font-semibold text-white">
          {t("recipeTitle")}
        </h3>
        <ol className="m-0 flex flex-col gap-1.5 pl-[18px] font-mono text-[13px] leading-normal">
          {STEPS.map((s) => (
            <li key={s}>{s}</li>
          ))}
          <li className="text-ink-accent">{convertStep(target)}</li>
        </ol>
        <Tabs
          variant="dark"
          label={t("recipeTabs")}
          items={(["pandas", "sql", "json"] as const).map((f) => ({
            value: f,
            label: f === "pandas" ? "pandas" : f.toUpperCase(),
            content: <CodeBlock code={snippets[f]} label={t("codeLabel", { format: f })} />,
          }))}
        />
        <Button variant="inverse">{t("export")}</Button>
        <p className="m-0 text-[13px] text-ink-dim">{t("replayNote")}</p>
      </section>
    </div>
  );
}
