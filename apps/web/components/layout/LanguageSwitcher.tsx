"use client";

import { useLocale, useTranslations } from "next-intl";
import { routing, Link, usePathname } from "@/i18n/routing";
import { cn } from "@/lib/cn";

/**
 * EN | ES switcher (header, right side, before API docs — ROADMAP Phase 2 i18n additions).
 * Keeps the current path; next-intl stores the choice in the NEXT_LOCALE cookie.
 */
export function LanguageSwitcher() {
  const t = useTranslations("common.languageSwitcher");
  const current = useLocale();
  const pathname = usePathname();

  return (
    <nav aria-label={t("label")} className="focus-on-dark">
      <ul className="m-0 flex list-none gap-1 p-0">
        {routing.locales.map((locale) => {
          const active = locale === current;
          return (
            <li key={locale}>
              <Link
                href={pathname}
                locale={locale}
                hrefLang={locale}
                lang={locale}
                aria-current={active ? "true" : undefined}
                aria-label={t(`names.${locale}`)}
                className={cn(
                  "inline-flex min-h-touch min-w-touch items-center justify-center rounded-nav px-3 text-sm uppercase no-underline",
                  active
                    ? "bg-ink-raised font-medium text-white hover:text-white"
                    : "text-ink-text hover:bg-ink-raised hover:text-white",
                )}
              >
                {locale}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
