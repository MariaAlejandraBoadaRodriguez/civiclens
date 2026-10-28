import { useTranslations } from "next-intl";

/** Cold-start state for the free-tier API (ROADMAP §2: Render cold start ~30–60 s). */
export function WakingUp() {
  const t = useTranslations("common.wakingUp");
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-4 rounded-card border border-primary-border bg-primary-soft p-5 text-primary-dark"
    >
      <span
        aria-hidden="true"
        className="mt-0.5 h-6 w-6 shrink-0 animate-spin rounded-full border-[3px] border-primary-border border-t-primary"
      />
      <div className="flex flex-col gap-1">
        <p className="m-0 text-[15px] font-semibold">{t("title")}</p>
        <p className="m-0 text-sm text-text">{t("body")}</p>
      </div>
    </div>
  );
}
