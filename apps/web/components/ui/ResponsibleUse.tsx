import { useId } from "react";
import { useLocale, useTranslations } from "next-intl";
import { cn } from "@/lib/cn";

const DOCS = "https://github.com/MariaAlejandraBoadaRodriguez/civiclens/blob/main/docs";

/** Responsible-use notice (red flags, dashboard; the reports carry the same text): flags are
 * leads for review, verify with the original source, data shown exactly as published. */
export function ResponsibleUse({ className }: { className?: string }) {
  const t = useTranslations("common.responsible");
  const locale = useLocale();
  const id = useId();
  const doc = `${DOCS}/${locale === "es" ? "responsible-use.es.md" : "responsible-use.md"}`;
  return (
    <aside
      aria-labelledby={id}
      data-testid="responsible-use"
      className={cn("flex flex-col gap-1.5 rounded-card border border-line bg-subtle px-[18px] py-3.5 text-sm leading-relaxed text-text", className)}
    >
      <h2 id={id} className="m-0 text-sm font-semibold text-ink">
        {t("title")}
      </h2>
      <ul className="m-0 flex flex-col gap-1 pl-5">
        <li>{t("leads")}</li>
        <li>{t("verify")}</li>
        <li>{t("asPublished")}</li>
      </ul>
      <a href={doc} className="self-start underline underline-offset-2">
        {t("link")}
      </a>
    </aside>
  );
}
