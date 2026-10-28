import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Header() {
  const t = useTranslations("common");
  return (
    <header className="bg-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2 focus:text-white">
        {t("skipToContent")}
      </a>
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-6 py-3.5">
        <Link href="/" className="text-lg font-semibold text-white no-underline">
          {t("brand")}
        </Link>
        <LanguageSwitcher />
      </div>
    </header>
  );
}
