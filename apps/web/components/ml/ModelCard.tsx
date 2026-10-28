import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Alert } from "@/components/ui/Alert";
import type { ModelCard as Card } from "@/lib/api-types";

/** Model card (spec M6): business question, method, rules, features, warning, limitations. */
export function ModelCard({ card, id, actions }: { card: Card; id: string; actions?: ReactNode }) {
  const t = useTranslations("ml.card");
  const row = "flex flex-col gap-1";
  const label = "text-[13px] font-medium text-muted";
  return (
    <section
      aria-labelledby={id}
      className="flex min-w-0 flex-[1_1_300px] flex-col gap-4 rounded-card border border-line bg-surface p-[22px]"
    >
      <h2 id={id} className="m-0 text-lg font-semibold text-ink">
        {t("title")}
      </h2>
      <div className={row}>
        <span className={label}>{t("question")}</span>
        <span className="text-[15px]">{card.question}</span>
      </div>
      <div className={row}>
        <span className={label}>{t("method")}</span>
        <span className="text-[15px]">{card.method}</span>
        {card.method_detail && <span className="text-[13px] leading-relaxed text-muted">{card.method_detail}</span>}
      </div>
      {card.rules && (
        <div className={row}>
          <span className={label}>{t("rules")}</span>
          <ul className="m-0 flex flex-col gap-1 pl-5 text-sm">
            {card.rules.map((r) => (
              <li key={r.id}>{r.label}</li>
            ))}
          </ul>
          {card.thresholds && <span className="text-[13px] text-muted">{card.thresholds}</span>}
        </div>
      )}
      <div className={row}>
        <span className={label}>{t("features")}</span>
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {card.features.map((f) => (
            <li key={f.id}>
              <span title={f.label} className="inline-block rounded-chip bg-subtle px-2 py-1 font-mono text-xs text-neutral">
                {f.id}
              </span>
              <span className="sr-only">: {f.label}</span>
            </li>
          ))}
        </ul>
      </div>
      <Alert variant="warning">{card.warning}</Alert>
      <details className="text-sm">
        <summary className="min-h-touch cursor-pointer content-center text-primary">{t("limitations")}</summary>
        <ul className="m-0 flex flex-col gap-1.5 pl-5 text-[13px] leading-relaxed text-muted">
          {card.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </details>
      {actions}
    </section>
  );
}
