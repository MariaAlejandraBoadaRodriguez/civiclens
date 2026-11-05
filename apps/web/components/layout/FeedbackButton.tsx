"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname } from "@/i18n/routing";

const REPO_URL = "https://github.com/MariaAlejandraBoadaRodriguez/civiclens";

/** GitHub issue form (.github/ISSUE_TEMPLATE/feedback.yml) with the page and language
 * pre-filled. Feedback lives in public GitHub issues: the app itself stores nothing. */
export function feedbackUrl(page: string, locale: string): string {
  const params = new URLSearchParams({ template: "feedback.yml", page, language: locale });
  return `${REPO_URL}/issues/new?${params.toString()}`;
}

export function FeedbackButton() {
  const t = useTranslations("common.feedback");
  const locale = useLocale();
  const pathname = usePathname();
  return (
    <a
      href={feedbackUrl(`/${locale}${pathname === "/" ? "" : pathname}`, locale)}
      target="_blank"
      rel="noopener"
      data-testid="feedback-button"
      className="inline-flex min-h-touch items-center gap-2 rounded-nav bg-ink-accent px-3 text-sm font-medium text-ink no-underline hover:bg-white hover:text-ink"
    >
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      {t("button")}
      <span className="sr-only">{t("newTab")}</span>
    </a>
  );
}
