import { getTranslations, setRequestLocale } from "next-intl/server";
import { buttonClass } from "@/components/ui/Button";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { DataTable } from "@/components/ui/DataTable";
import { Tabs } from "@/components/ui/Tabs";
import { Link } from "@/i18n/routing";
import { PUBLIC_API_URL } from "@/lib/api";

type Params = { params: { locale: string } };

export async function generateMetadata({ params: { locale } }: Params) {
  const t = await getTranslations({ locale, namespace: "developers" });
  return { title: t("metaTitle"), description: t("subtitle") };
}

const REPO_URL = "https://github.com/MariaAlejandraBoadaRodriguez/civiclens";
/** Endpoint reference: method and path are machine values; the description is translated. */
const ENDPOINTS = [
  ["POST", "/api/v1/datasets", "upload"],
  ["GET", "/api/v1/jobs/{job_id}", "job"],
  ["GET", "/api/v1/datasets/{id}/profile", "profile"],
  ["GET", "/api/v1/datasets/{id}/issues", "issues"],
  ["POST", "/api/v1/datasets/{id}/recipes/apply", "apply"],
  ["GET", "/api/v1/datasets/{id}/download", "download"],
  ["GET | PUT", "/api/v1/datasets/{id}/domain", "domain"],
  ["GET", "/api/v1/guided-queries?dataset_id={id}", "guided"],
  ["POST", "/api/v1/query", "query"],
  ["GET", "/api/v1/kpis/{id}", "kpis"],
  ["POST", "/api/v1/models/{model}/run", "models"],
  ["GET", "/api/v1/datasets/{id}/overview", "overview"],
  ["POST", "/api/v1/datasets/{id}/chart", "chart"],
  ["GET", "/api/v1/reports/{id}?lang=es&format=pdf", "report"],
  ["GET", "/api/v1/datasets/{id}/export?format=parquet", "export"],
] as const;

export default async function DevelopersPage({ params: { locale } }: Params) {
  setRequestLocale(locale);
  const t = await getTranslations("developers");
  const api = PUBLIC_API_URL;
  const lang = locale === "es" ? "es" : "en";

  // Code is never translated; only the comment lines follow the UI language.
  const steps = [
    {
      key: "upload",
      curl: [
        `# ${t("code.upload")}`,
        `curl -X POST ${api}/api/v1/datasets \\`,
        `  -H "X-API-Key: $CIVICLENS_KEY" -H "Accept-Language: ${lang}" \\`,
        `  -F "file=@my_data.csv"`,
        `# ${t("code.poll")}`,
        `curl ${api}/api/v1/jobs/$JOB_ID`,
      ],
      python: [
        "import requests, time",
        `API = "${api}"`,
        `H = {"X-API-Key": KEY, "Accept-Language": "${lang}"}`,
        `# ${t("code.upload")}`,
        `r = requests.post(f"{API}/api/v1/datasets", headers=H, files={"file": open("my_data.csv", "rb")})`,
        `dataset, job = r.json()["dataset"]["id"], r.json()["job"]["id"]`,
        `# ${t("code.poll")}`,
        `while requests.get(f"{API}/api/v1/jobs/{job}", headers=H).json()["status"] not in ("succeeded", "failed"):`,
        "    time.sleep(1)",
      ],
    },
    {
      key: "explore",
      curl: [
        `# ${t("code.domain")}`,
        `curl -H "Accept-Language: ${lang}" ${api}/api/v1/datasets/$DATASET_ID/domain`,
        `# ${t("code.guided")}`,
        `curl "${api}/api/v1/guided-queries?dataset_id=$DATASET_ID"`,
        `# ${t("code.query")}`,
        `curl -X POST ${api}/api/v1/query -H "Content-Type: application/json" \\`,
        `  -d '{"dataset_id": "'$DATASET_ID'", "sql": "SELECT COUNT(*) FROM data"}'`,
      ],
      python: [
        `# ${t("code.domain")}`,
        `domain = requests.get(f"{API}/api/v1/datasets/{dataset}/domain", headers=H).json()`,
        `print(domain["pack"], domain["roles"])`,
        `# ${t("code.guided")}`,
        `questions = requests.get(f"{API}/api/v1/guided-queries", params={"dataset_id": dataset}, headers=H).json()["items"]`,
        `# ${t("code.query")}`,
        `rows = requests.post(f"{API}/api/v1/query", headers=H,`,
        `                     json={"dataset_id": dataset, "sql": questions[0]["sql"]}).json()["rows"]`,
      ],
    },
    {
      key: "results",
      curl: [
        `# ${t("code.model")}`,
        `curl -X POST ${api}/api/v1/models/target_model/run -H "X-API-Key: $CIVICLENS_KEY" \\`,
        `  -H "Content-Type: application/json" -d '{"dataset_id": "'$DATASET_ID'"}'`,
        `# ${t("code.overview")}`,
        `curl -H "Accept-Language: ${lang}" ${api}/api/v1/datasets/$DATASET_ID/overview`,
        `# ${t("code.report")}`,
        `curl -o report.pdf "${api}/api/v1/reports/$DATASET_ID?lang=${lang}&format=pdf"`,
      ],
      python: [
        `# ${t("code.model")}`,
        `requests.post(f"{API}/api/v1/models/target_model/run", headers=H, json={"dataset_id": dataset})`,
        `card = requests.get(f"{API}/api/v1/models/target_model/latest", params={"dataset_id": dataset}, headers=H).json()["card"]`,
        `# ${t("code.overview")}`,
        `for section in requests.get(f"{API}/api/v1/datasets/{dataset}/overview", headers=H).json()["sections"]:`,
        `    print(section["title"], "—", section["finding"])`,
        `# ${t("code.report")}`,
        `open("report.pdf", "wb").write(requests.get(f"{API}/api/v1/reports/{dataset}", params={"lang": "${lang}", "format": "pdf"}).content)`,
      ],
    },
  ];

  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-8 px-6 pb-12 pt-8">
      <section aria-labelledby="dev-title" className="focus-on-dark flex flex-col gap-4 rounded-card bg-ink p-8 text-ink-text">
        <p className="m-0 font-mono text-[13px] text-ink-accent">{t("eyebrow")}</p>
        <h1 id="dev-title" className="m-0 text-[32px] font-semibold text-white">
          {t("title")}
        </h1>
        <p className="m-0 max-w-[720px] text-base leading-relaxed">{t("subtitle")}</p>
        <div className="flex flex-wrap gap-3">
          <a href={`${api}/docs`} className={buttonClass("inverse")}>
            {t("explorer")}
          </a>
          <a href={`${REPO_URL}/blob/main/openapi.yaml`} className="inline-flex min-h-touch items-center rounded-control border border-ink-line px-4 text-[15px] text-white no-underline hover:border-ink-text hover:text-white">
            {t("spec")}
          </a>
          <Link href="/admin" className="inline-flex min-h-touch items-center rounded-control border border-ink-line px-4 text-[15px] text-white no-underline hover:border-ink-text hover:text-white">
            {t("key")}
          </Link>
        </div>
      </section>

      <section aria-labelledby="steps" className="flex flex-col gap-5">
        <h2 id="steps" className="m-0 text-2xl font-semibold text-ink">
          {t("steps.title")}
        </h2>
        <ol className="m-0 flex list-none flex-col gap-5 p-0">
          {steps.map((step, i) => (
            <li key={step.key} className="flex flex-col gap-3 rounded-card border border-line bg-surface p-[22px]" data-testid="dev-step">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-[15px] text-primary" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="flex flex-col gap-1">
                  <h3 className="m-0 text-lg font-semibold text-ink">{t(`steps.${step.key}.title`)}</h3>
                  <p className="m-0 text-[15px] leading-relaxed text-text">{t(`steps.${step.key}.body`)}</p>
                </div>
              </div>
              <Tabs
                label={t("languageTabs")}
                items={[
                  { value: "curl", label: "curl", content: <CodeBlock code={step.curl.join("\n")} label={t("codeLabel", { lang: "curl" })} /> },
                  { value: "python", label: "Python", content: <CodeBlock code={step.python.join("\n")} label={t("codeLabel", { lang: "Python" })} /> },
                ]}
              />
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="conventions" className="flex flex-col gap-3">
        <h2 id="conventions" className="m-0 text-2xl font-semibold text-ink">
          {t("conventions.title")}
        </h2>
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-2">
          {(["auth", "language", "errors", "limits"] as const).map((k) => (
            <li key={k} className="flex flex-col gap-1 rounded-card border border-line bg-surface p-4">
              <h3 className="m-0 text-base font-semibold text-ink">{t(`conventions.${k}.title`)}</h3>
              <p className="m-0 text-sm leading-relaxed text-text">{t(`conventions.${k}.body`)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="endpoints" className="flex flex-col gap-3">
        <h2 id="endpoints" className="m-0 text-2xl font-semibold text-ink">
          {t("endpoints.title")}
        </h2>
        <DataTable
          caption={t("endpoints.caption")}
          captionHidden
          minWidth={640}
          rows={[...ENDPOINTS]}
          rowKey={(e) => `${e[0]} ${e[1]}`}
          columns={[
            { key: "method", header: t("endpoints.method"), mono: true, cell: (e) => e[0] },
            { key: "path", header: t("endpoints.path"), mono: true, cell: (e) => e[1] },
            { key: "what", header: t("endpoints.what"), cell: (e) => t(`endpoints.items.${e[2]}`) },
          ]}
        />
        <p className="m-0 text-sm text-muted">{t("endpoints.more")}</p>
      </section>
    </main>
  );
}
