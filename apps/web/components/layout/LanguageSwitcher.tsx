"use client";

import { useLocale, useTranslations } from "next-intl";
import { routing } from "@/i18n/routing";
import { Link, usePathname } from "@/i18n/routing";

export function LanguageSwitcher() {
  const t = useTranslations("common");
  const current = useLocale();
  const pathname = usePathname();

  return (
    <nav aria-label={t("language")} className="flex gap-1">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href={pathname}
          locale={locale}
          aria-current={locale === current ? "true" : undefined}
          className={`rounded-md px-3 py-2 text-sm uppercase no-underline ${
            locale === current ? "bg-[#1E3A5F] text-white" : "text-[#C9D3E0]"
          }`}
        >
          {locale}
        </Link>
      ))}
    </nav>
  );
}
