import { MESSAGES, expect, test, type Lang } from "./fixtures";

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
      await expect(page).toHaveURL(new RegExp(`/${lang}/datasets/[0-9a-f-]{36}$`), { timeout: 120_000 });
      await expect(page.getByRole("heading", { level: 1, name: m.ingest.title })).toBeVisible();
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

    test("ML lab → red flags and forecast", async ({ page }) => {
      await page.goto(`/${lang}/datasets/contracts_qc/ml`);
      await expect(page.getByRole("heading", { level: 2, name: m.ml.flags.title })).toBeVisible({ timeout: 150_000 });
      await page.getByRole("tab", { name: m.ml.tabs.forecast }).click();
      await expect(page.getByRole("heading", { level: 2, name: m.ml.forecast.title })).toBeVisible({ timeout: 150_000 });
    });
  });
}
