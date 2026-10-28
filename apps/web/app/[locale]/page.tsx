import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";

export default function LandingPage({ params: { locale } }: { params: { locale: string } }) {
  setRequestLocale(locale);
  const t = useTranslations("landing");

  return (
    <main id="main" className="mx-auto flex max-w-[1200px] flex-col gap-5 px-6 py-16">
      <p className="font-mono text-[13px] uppercase tracking-wide text-primary">{t("eyebrow")}</p>
      <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-ink md:text-5xl">{t("title")}</h1>
      <p className="max-w-2xl text-lg leading-relaxed text-muted">{t("subtitle")}</p>
      <p className="w-fit rounded-md bg-flag-tint px-3 py-2 text-sm text-flag-text">{t("status")}</p>
    </main>
  );
}
