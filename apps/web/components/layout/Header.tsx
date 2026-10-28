import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { LifecycleNav } from "./LifecycleNav";

const API_DOCS_URL = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/docs`;

export function Header() {
  const t = useTranslations("common");
  return (
    <header className="focus-on-dark bg-ink">
      <a
        href="#main"
        className="sr-only z-10 rounded-nav bg-surface px-3 py-2 text-ink focus:not-sr-only focus:absolute focus:left-2 focus:top-2"
      >
        {t("skipToContent")}
      </a>
      <div className="mx-auto flex max-w-container flex-wrap items-center gap-x-7 gap-y-3 px-6 py-3.5">
        <Link
          href="/"
          className="flex min-h-touch items-center gap-2.5 text-lg font-semibold text-white no-underline hover:text-white"
        >
          <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-ink-accent">
            <circle cx="11" cy="11" r="7" />
            <path d="M16 16l5 5" />
            <path d="M8 13v-2M11 13V8M14 13v-4" />
          </svg>
          {t("brand")}
        </Link>
        <LifecycleNav />
        <div className="flex flex-wrap items-center gap-3">
          <LanguageSwitcher />
          <a
            href={API_DOCS_URL}
            className="inline-flex min-h-touch items-center rounded-nav border border-ink-line px-3 text-sm text-ink-text no-underline hover:border-ink-text hover:text-white"
          >
            {t("apiDocs")}
          </a>
        </div>
      </div>
    </header>
  );
}
