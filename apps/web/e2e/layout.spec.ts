import { MESSAGES, expect, test, type Lang } from "./fixtures";

/**
 * Phase 6 DoD: no clipped or overflowing text in either language at 375 px and 1280 px.
 * Fails when the page scrolls sideways, or when an element cuts its own text (overflow hidden /
 * ellipsis with content wider or taller than the box). Scroll regions (tables, code, charts) are
 * allowed: they scroll on purpose and are keyboard-reachable.
 */
const PAGES = [
  "",
  "/datasets/secop_co",
  "/datasets/contracts_ca/clean",
  "/datasets/contracts_qc/sql",
  "/datasets/secop_co/ml",
  "/datasets/contracts_ca/dashboard?scope=all&period=12m",
  "/datasets/secop_co/dashboard",
  "/admin",
];
function findClipping(): string[] {
  const out: string[] = [];
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    out.push(`page scrolls sideways: ${document.documentElement.scrollWidth}px`);
  }
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("main *, header *"))) {
    if (el.closest("[role=region], pre, svg, details:not([open]), .sr-only, select")) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const clipsX = ["hidden", "clip"].includes(style.overflowX) || style.textOverflow === "ellipsis";
    const clipsY = ["hidden", "clip"].includes(style.overflowY);
    const text = (el.innerText || "").trim();
    if (!text) continue;
    if ((clipsX && el.scrollWidth > el.clientWidth + 1) || (clipsY && el.scrollHeight > el.clientHeight + 1)) {
      out.push(`clipped: <${el.tagName.toLowerCase()}> "${text.slice(0, 60)}"`);
    }
  }
  return out;
}

const LANGS: Lang[] = ["en", "es"];
const WIDTHS = [375, 1280];

for (const width of WIDTHS) {
  for (const lang of LANGS) {
    test(`no clipped text at ${width}px in /${lang}`, async ({ page }) => {
      test.setTimeout(300_000);
      await page.setViewportSize({ width, height: 900 });
      for (const path of PAGES) {
        await page.goto(`/${lang}${path}`);
        await page.waitForLoadState("networkidle");
        const problems = await page.evaluate(findClipping);
        expect(problems, `/${lang}${path} at ${width}px`).toEqual([]);
      }
    });
  }
}

test("the clipping check catches clipped text and sideways scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 600 });
  await page.setContent(
    `<main><p style="width:80px;overflow:hidden;white-space:nowrap">Presupuesto ejecutado por entidad</p>` +
      `<div style="width:900px">wide</div></main>`,
  );
  const problems = await page.evaluate(findClipping);
  expect(problems.some((p) => p.startsWith("page scrolls sideways"))).toBe(true);
  expect(problems.some((p) => p.includes("Presupuesto ejecutado"))).toBe(true);
});

for (const lang of LANGS) {
  test(`unknown pages are a translated 404 in /${lang}`, async ({ page, browserConsole }) => {
    browserConsole.allow(/status of 404/); // the browser logs the 404 response itself
    const res = await page.goto(`/${lang}/no-such-page`);
    expect(res?.status()).toBe(404);
    const m = MESSAGES[lang];
    await expect(page.getByRole("heading", { level: 1, name: m.common.notFoundPage.title })).toBeVisible();
    await expect(page.getByRole("navigation").first()).toBeVisible(); // inside the app layout
  });
}
