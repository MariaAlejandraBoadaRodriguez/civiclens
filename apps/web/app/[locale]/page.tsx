import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { TryAnyData } from "@/components/ingest/TryAnyData";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Link } from "@/i18n/routing";

const REPO_URL = "https://github.com/MariaAlejandraBoadaRodriguez/civiclens";

const STEPS = [
  { key: "ingest", href: "/datasets/secop_co" },
  { key: "clean", href: "/datasets/secop_co/clean" },
  { key: "sql", href: "/datasets/secop_co/sql" },
  { key: "ml", href: "/datasets/secop_co/ml" },
  { key: "report", href: "/datasets/secop_co/dashboard" },
] as const;

const OUTPUTS = ["quality", "recipe", "star", "flags", "report"] as const;

// Data language and file format are machine values: shown as codes in both UI languages.
const ANY_FORMAT = "CSV";
const SAMPLES = [
  { slug: "secop_co", lang: "ES", format: "CSV" },
  { slug: "contracts_ca", lang: "EN / FR", format: "XLSX" },
  { slug: "contracts_qc", lang: "FR", format: "JSON" },
] as const;

export default function LandingPage({ params: { locale } }: { params: { locale: string } }) {
  setRequestLocale(locale);
  const t = useTranslations("landing");

  return (
    <>
      <main id="main" className="mx-auto flex max-w-container flex-col gap-14 px-6 pb-12 pt-12 md:pt-16">
        <section className="flex flex-wrap items-center gap-10">
          <div className="flex min-w-0 flex-[999_1_520px] flex-col gap-5">
            <p className="m-0 font-mono text-[13px] uppercase tracking-wide text-primary">{t("eyebrow")}</p>
            <h1 className="m-0 text-4xl font-semibold leading-tight text-ink md:text-5xl">{t("title")}</h1>
            <p className="m-0 max-w-[600px] text-lg leading-relaxed text-muted">{t("subtitle")}</p>
            <div className="flex flex-wrap gap-3">
              <ButtonLink href="/datasets/secop_co">{t("trySample")}</ButtonLink>
              <ButtonLink href="/datasets/secop_co#source" variant="secondary">
                {t("upload")}
              </ButtonLink>
            </div>
          </div>
          <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-3.5 rounded-card border border-line bg-surface p-6">
            <h2 className="m-0 text-[13px] font-medium text-muted">{t("outputs.title")}</h2>
            <dl className="m-0 flex flex-col">
              {OUTPUTS.map((key) => (
                <div key={key} className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-b border-subtle py-2.5 last:border-0">
                  <dt className="text-[15px]">{t(`outputs.${key}.label`)}</dt>
                  <dd className="m-0 font-mono text-[15px] text-ink">{t(`outputs.${key}.value`)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section aria-labelledby="flow" className="flex flex-col gap-5">
          <h2 id="flow" className="m-0 text-2xl font-semibold text-ink">
            {t("flow.title")}
          </h2>
          <ol className="m-0 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-5">
            {STEPS.map((step, i) => (
              <li key={step.key} className="flex">
                <Link
                  href={step.href}
                  className="flex w-full flex-col gap-2 rounded-card border border-line bg-surface p-5 text-text no-underline hover:border-primary hover:text-text"
                >
                  <span className="font-mono text-[13px] text-primary" aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-[17px] font-semibold text-ink">{t(`flow.${step.key}.title`)}</span>
                  <span className="text-sm leading-normal text-muted">{t(`flow.${step.key}.body`)}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="samples" className="flex flex-col gap-5">
          <h2 id="samples" className="m-0 text-2xl font-semibold text-ink">
            {t("samples.title")}
          </h2>
          <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 md:grid-cols-2 xl:grid-cols-4">
            {SAMPLES.map((s) => (
              <li key={s.slug} className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[22px]">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="language">{s.lang}</Badge>
                  <Badge>{s.format}</Badge>
                </div>
                <h3 className="m-0 text-lg font-semibold text-ink">{t(`samples.${s.slug}.name`)}</h3>
                <p className="m-0 text-sm leading-normal text-muted">{t(`samples.${s.slug}.body`)}</p>
                <Link href={`/datasets/${s.slug}`} className="mt-auto inline-flex min-h-touch items-center text-[15px] font-medium">
                  {t("samples.use")}
                  <span className="sr-only">{t("samples.useFor", { name: t(`samples.${s.slug}.name`) })}</span>
                </Link>
              </li>
            ))}
            <li className="flex flex-col gap-3 rounded-card border-2 border-primary bg-primary-soft p-[22px]" data-testid="any-data-card">
              <div className="flex flex-wrap gap-2">
                <Badge variant="info">{t("samples.anyData.badge")}</Badge>
                <Badge>{ANY_FORMAT}</Badge>
              </div>
              <h3 className="m-0 text-lg font-semibold text-ink">{t("samples.anyData.name")}</h3>
              <p className="m-0 text-sm leading-normal text-muted">{t("samples.anyData.body")}</p>
              <p className="m-0 text-xs text-muted">{t("samples.anyData.license")}</p>
              <TryAnyData />
            </li>
          </ul>
        </section>
      </main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-container flex-wrap justify-between gap-3 px-6 py-5 text-sm text-muted">
          <span>{t("footer.builtBy")}</span>
          <span className="flex flex-wrap gap-x-5 gap-y-1">
            <a href={REPO_URL} className="inline-flex min-h-touch items-center">
              {t("footer.github")}
            </a>
            <a href={`${REPO_URL}/blob/main/data/seed/README.md`} className="inline-flex min-h-touch items-center">
              {t("footer.licenses")}
            </a>
            <Link href="/design" className="inline-flex min-h-touch items-center">
              {t("footer.design")}
            </Link>
          </span>
        </div>
      </footer>
    </>
  );
}
