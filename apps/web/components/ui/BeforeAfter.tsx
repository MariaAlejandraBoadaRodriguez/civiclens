import { useTranslations } from "next-intl";

/** Before/After preview of a cleaning decision. Values are data, shown as-is in mono. */
export function BeforeAfter({
  before,
  after,
  afterLabel,
}: {
  before: string[];
  after: string[];
  /** Suffix for the After title, e.g. the target currency. */
  afterLabel?: string;
}) {
  const t = useTranslations("common");
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-live="polite">
      <div className="flex flex-col gap-2 rounded-panel border border-line p-3.5">
        <span className="text-[13px] font-medium text-muted">{t("before")}</span>
        {before.map((v, i) => (
          <span key={i} className="break-all font-mono text-sm">
            {v}
          </span>
        ))}
      </div>
      <div className="flex flex-col gap-2 rounded-panel border border-primary-border bg-primary-soft p-3.5">
        <span className="text-[13px] font-medium text-primary-dark">
          {afterLabel ? t("afterWith", { label: afterLabel }) : t("after")}
        </span>
        {after.map((v, i) => (
          <span key={i} className="break-all font-mono text-sm">
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}
