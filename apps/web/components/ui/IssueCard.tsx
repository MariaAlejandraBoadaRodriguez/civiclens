import type { ReactNode } from "react";
import { useTranslations } from "next-intl";

/**
 * Cleaning-studio issue card (mockup screen 2, center column).
 * Texts arrive localized from the API catalogs (ADR-0007); options/preview are slots
 * so the parent can wire live updates.
 */
export function IssueCard({
  id,
  eyebrow,
  title,
  found,
  why,
  options,
  preview,
  impact,
  actions,
}: {
  id: string;
  eyebrow: string;
  title: string;
  found: ReactNode;
  why: ReactNode;
  options?: ReactNode;
  preview?: ReactNode;
  impact?: { label: string; before: string; after: string; note?: string };
  actions?: ReactNode;
}) {
  const t = useTranslations("common");
  return (
    <section
      aria-labelledby={id}
      className="flex min-w-0 flex-col gap-5 rounded-card border border-line bg-surface p-6"
    >
      <div className="flex flex-col gap-2">
        <span className="font-mono text-xs uppercase text-flag">{eyebrow}</span>
        <h2 id={id} className="m-0 text-[22px] font-semibold text-ink">
          {title}
        </h2>
        <p className="m-0 text-[15px] leading-relaxed">
          <strong className="font-semibold">{t("whatWeFound")}</strong> {found}
        </p>
        <p className="m-0 text-[15px] leading-relaxed">
          <strong className="font-semibold">{t("whyItMatters")}</strong> {why}
        </p>
      </div>
      {options}
      {preview}
      {impact && (
        <div className="flex flex-wrap items-center gap-3 rounded-panel bg-ground px-4 py-3.5">
          <span className="text-sm text-muted">{impact.label}</span>
          <span className="font-mono text-[15px] text-muted line-through">{impact.before}</span>
          <span aria-hidden="true">→</span>
          <span className="sr-only">{t("becomes")}</span>
          <span className="font-mono text-[15px] font-medium text-ink">{impact.after}</span>
          {impact.note && <span className="basis-full text-[13px] text-muted">{impact.note}</span>}
        </div>
      )}
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </section>
  );
}
