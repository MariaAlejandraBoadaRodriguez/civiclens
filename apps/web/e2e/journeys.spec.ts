import path from "node:path";
import { MESSAGES, expect, test, type Lang } from "./fixtures";

/** Acceptance fixtures (data/fixtures/README.md): public, non-procurement files. */
const FIXTURES = path.resolve(__dirname, "../../../data/fixtures");

const LANGS: Lang[] = ["en", "es"];

for (const lang of LANGS) {
  const m = MESSAGES[lang];

  test.describe(`${lang}`, () => {
    test("landing → sample dataset profile", async ({ page }) => {
      await page.goto(`/${lang}`);
      await page.getByRole("link", { name: m.landing.trySample }).click();
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/secop_co$`));
      await expect(page.getByRole("heading", { level: 1, name: m.ingest.title })).toBeVisible();
      await expect(page.getByText(m.ingest.score.title).first()).toBeVisible();
    });

    test("upload a file → its profile", async ({ page }) => {
      await page.goto(`/${lang}/datasets/secop_co`);
      const rows = Array.from({ length: 40 }, (_, i) => `C-${i};Entidad ${i % 4};Proveedor ${i % 7};2024-0${(i % 9) + 1}-15;${1000 + i},50`);
      await page.locator("input[type=file]").setInputFiles({
        name: `contratos-${lang}.csv`,
        mimeType: "text/csv",
        buffer: Buffer.from(["id_contrato;entidad;proveedor;fecha_firma;valor", ...rows].join("\n")),
      });
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/[0-9a-f-]{36}\\?ready=1$`), { timeout: 120_000 });
      await expect(page.getByRole("heading", { level: 1, name: m.ingest.title })).toBeVisible();
      // The finished upload is announced with the large green banner.
      const banner = page.getByTestId("banner-success");
      await expect(banner).toContainText(m.ingest.ready.title.replace("{name}", `contratos-${lang}.csv`));
      await expect(banner.getByRole("link", { name: m.ingest.ready.next })).toBeVisible();
    });

    test("any dataset: credit file → banking domain suggested and confirmed → generic SQL lab", async ({ page }) => {
      await page.goto(`/${lang}/datasets/secop_co`);
      await page.locator("input[type=file]").setInputFiles(path.join(FIXTURES, "german_credit.csv"));
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/[0-9a-f-]{36}\\?ready=1$`), { timeout: 120_000 });
      // The domain step suggests Banking and maps the target with a confidence.
      const step = page.locator("section", { has: page.getByRole("heading", { name: m.domain.title }) });
      await expect(step.getByText(m.domain.suggested.replace("{name}", ""), { exact: false })).toBeVisible();
      await expect(step.getByRole("radio", { checked: true })).toHaveValue("banking");
      await expect(step.getByTestId("role-mapping")).toContainText("credit_risk");
      await step.getByRole("button", { name: m.domain.confirm }).click();
      const saved = step.getByTestId("banner-success");
      await expect(saved).toBeVisible({ timeout: 60_000 });
      await saved.getByRole("link", { name: m.domain.openSql }).click();
      // SQL lab: the table data with its columns, no star schema, and results for the first question.
      await expect(page.getByRole("heading", { level: 2, name: new RegExp(m.sql.data.title.split(" <")[0]) })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: m.sql.schema.title })).toHaveCount(0);
      await expect(page.getByTestId("active-domain")).toContainText(m.sql.domainChip.replace("{pack}", ""));
      const results = m.sql.results.title.split(" · ")[0];
      await expect(page.getByRole("heading", { level: 3, name: new RegExp(`^${results}`) })).toBeVisible();
      await expect(page.locator("#query-results table tbody tr").first()).toBeVisible();
    });

    test("cleaning studio → recipe preview → apply", async ({ page }) => {
      await page.goto(`/${lang}/datasets/contracts_ca/clean`);
      await expect(page.getByRole("heading", { level: 1, name: m.clean.title })).toBeVisible();
      // The recipe code panel is filled by POST /recipes/preview (the call that failed in production).
      await expect(page.locator("pre").filter({ hasText: "df" }).first()).toBeVisible();
      // Decide every issue with its recommended option, as a user following the studio would.
      const decide = page.getByRole("button", { name: m.clean.issue.apply });
      for (let n = 0; n < 20 && (await decide.isVisible()); n += 1) await decide.click();
      await page.getByRole("button", { name: m.clean.run.apply }).click();
      await expect(page.getByText(m.clean.run.quality)).toBeVisible({ timeout: 150_000 });
      // Success banner with the downloads: the cleaned data and the recipe.
      const banner = page.getByTestId("banner-success");
      await expect(banner).toBeVisible();
      const csv = await banner.getByRole("link", { name: m.clean.run.downloadCsv }).getAttribute("href");
      const res = await page.request.get(csv as string);
      expect(res.status()).toBe(200);
      expect(res.headers()["x-civiclens-origin"]).toBe("clean");
      expect((await res.text()).split("\n")[0].length).toBeGreaterThan(0);
      for (const f of ["json", "pandas", "sql"] as const) {
        await expect(banner.getByRole("link", { name: m.clean.run.downloadRecipe[f] })).toBeVisible();
      }
    });

    test("continue with unsaved cleaning decisions asks to apply first", async ({ page }) => {
      await page.goto(`/${lang}/datasets/secop_co/clean`);
      // The first issues (header mapping, personal data, duplicates) add recipe steps.
      for (let n = 0; n < 3; n += 1) await page.getByRole("button", { name: m.clean.issue.apply }).click();
      await page.getByRole("button", { name: m.clean.run.continue }).click();
      await expect(page.getByRole("alertdialog")).toBeVisible();
      await page.getByRole("button", { name: m.clean.run.unsaved.skip }).click();
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/secop_co/sql$`));
    });

    test("SQL lab → guided query results and a rejected query", async ({ page, browserConsole }) => {
      // The DROP below is rejected with a 400 on purpose; the browser logs that response.
      browserConsole.allow(/status of 400 .*\/api\/v1\/query$/);
      await page.goto(`/${lang}/datasets/secop_co/sql`);
      const results = m.sql.results.title.split(" · ")[0];
      await expect(page.getByRole("heading", { level: 3, name: new RegExp(`^${results}`) })).toBeVisible();
      await page.getByLabel(m.sql.editor.label).fill("DROP TABLE fact_contract");
      await page.getByRole("button", { name: m.sql.editor.run }).click();
      const notice = page.locator("#query-results").getByRole("alert");
      await expect(notice).toBeVisible();
      await expect(notice).not.toContainText(m.common.apiError.unavailableTitle); // a 400, not an outage
    });

    test("admin signs in, issues a scoped key, the API accepts it, then it is revoked", async ({ page, request }) => {
      const api = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
      await page.goto(`/${lang}/admin`);
      await expect(page.getByRole("heading", { level: 1, name: m.admin.title })).toBeVisible();
      await page.getByRole("button", { name: m.admin.signIn.testMode }).click();
      await expect(page.getByRole("button", { name: m.admin.signOut })).toBeVisible();
      const name = `E2E ${lang} ${Date.now()}`;
      await page.getByLabel(m.admin.form.name, { exact: true }).fill(name);
      await page.getByRole("button", { name: m.admin.form.create }).click();
      const field = page.getByLabel(m.admin.created.label);
      await expect(field).toHaveValue(/^cl_live_[0-9a-f]{8}\./);
      const key = await field.inputValue();
      // The key works against the API (default scope: reports:read)…
      const ok = await request.get(`${api}/api/v1/reports/contracts_ca?lang=${lang}`, { headers: { "X-API-Key": key } });
      expect(ok.status()).toBe(200);
      await page.getByRole("button", { name: m.admin.created.done }).click();
      await page.getByRole("button", { name: m.admin.list.revokeLabel.replace("{name}", name) }).click();
      await page.getByRole("button", { name: m.admin.list.confirmRevoke }).click();
      const row = page.getByTestId("api-key-row").filter({ hasText: name });
      await expect(row.getByText(m.admin.list.revoked, { exact: true })).toBeVisible();
      // …and is refused everywhere once revoked.
      const refused = await request.get(`${api}/api/v1/datasets`, { headers: { "X-API-Key": key, "Accept-Language": lang } });
      expect(refused.status()).toBe(401);
      await page.getByRole("button", { name: m.admin.signOut }).click();
      await expect(page.getByRole("button", { name: m.admin.signIn.testMode })).toBeVisible();
    });

    test("ML lab → red flags and forecast", async ({ page }) => {
      await page.goto(`/${lang}/datasets/contracts_qc/ml`);
      await expect(page.getByRole("heading", { level: 2, name: m.ml.flags.title })).toBeVisible({ timeout: 150_000 });
      await page.getByRole("tab", { name: m.ml.tabs.forecast }).click();
      await expect(page.getByRole("heading", { level: 2, name: m.ml.forecast.title })).toBeVisible({ timeout: 150_000 });
    });
    test("ML lab → dashboard → filters → executive report (HTML + PDF) and BI export", async ({ page, request }) => {
      await page.goto(`/${lang}/datasets/contracts_qc/ml`);
      await page.getByRole("link", { name: m.ml.continue }).click();
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/contracts_qc/dashboard$`));
      await expect(page.getByRole("heading", { level: 1, name: m.dashboard.title })).toBeVisible();
      await expect(page.getByTestId("kpi-tile")).toHaveCount(6);
      await expect(page.getByTestId("finding")).toContainText(m.dashboard.monthly.finding);
      // Filters update the URL and the figures; the comparison is always in CAD.
      await page.getByRole("combobox", { name: m.dashboard.filters.jurisdiction, exact: true }).selectOption("all");
      await page.getByRole("combobox", { name: m.dashboard.filters.period, exact: true }).selectOption("12m");
      await expect(page).toHaveURL(/scope=all/);
      await expect(page).toHaveURL(/period=12m/);
      await expect(page.getByTestId("kpi-tile").first()).toContainText(
        m.dashboard.kpi.change.replace("{value} ", ""),
      );
      await expect(page.getByTestId("jurisdiction-row")).toHaveCount(3);
      // The comparison uses the same filters as the tiles: its contracts add up to the tile.
      await expect(page.getByTestId("jurisdiction-filters")).toContainText(m.dashboard.filters.periods["12m"]);
      const digits = (text: string) => Number(text.replace(/\D/g, ""));
      const rows = await page.getByTestId("jurisdiction-row").locator("span.text-xs").allInnerTexts();
      const tile = await page.getByTestId("kpi-tile").nth(1).locator("span").nth(1).innerText();
      expect(rows.map(digits).reduce((a, b) => a + b, 0)).toBe(digits(tile));
      await page.getByRole("combobox", { name: m.dashboard.filters.category, exact: true }).selectOption("goods");
      await expect(page).toHaveURL(/category=goods/);
      await expect(page.getByTestId("jurisdiction-filters")).toContainText(m.dashboard.filters.categories.goods);
      // The report is generated in the UI language, as HTML and as PDF.
      const report = page.getByRole("link", { name: new RegExp(m.dashboard.actions.report) });
      const href = await report.getAttribute("href");
      expect(href).toContain(`lang=${lang}`);
      const html = await request.get(href as string);
      expect(html.status()).toBe(200);
      expect(await html.text()).toContain(`<html lang="${lang}">`);
      const pdfHref = await page.getByRole("link", { name: new RegExp(m.dashboard.actions.pdf) }).getAttribute("href");
      const pdf = await request.get(pdfHref as string);
      expect(pdf.headers()["content-type"]).toBe("application/pdf");
      expect(pdf.headers()["content-language"]).toBe(lang);
      const zip = await request.get((await page.getByRole("link", { name: m.dashboard.actions.export }).getAttribute("href")) as string);
      expect(zip.headers()["content-type"]).toBe("application/zip");
      // Lifecycle nav: step 5 is a real link now.
      await expect(page.getByRole("navigation", { name: m.nav.lifecycle }).getByRole("link", { name: new RegExp(m.nav.dashboard) })).toHaveAttribute("aria-current", "page");
    });
  });
}
