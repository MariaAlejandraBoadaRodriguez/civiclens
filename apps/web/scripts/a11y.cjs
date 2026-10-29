/**
 * axe-core audit of the design-system pages in both locales (Phase 3 DoD).
 * Usage: npm run build && npm start &  then  npm run test:a11y [baseUrl]
 * Dataset pages need the API (API_URL) to render real data; without it they show the
 * "Waking up the engine" state, which is audited too.
 * Requires the Playwright Chromium build (`npx playwright install chromium`; CI job "a11y").
 */
const path = require("node:path");
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://localhost:3000";
const PAGES = ["/en/design", "/es/design", "/en", "/es", "/en/datasets/secop_co", "/es/datasets/contracts_qc", "/en/datasets/contracts_ca/clean", "/es/datasets/secop_co/clean", "/en/datasets/secop_co/sql", "/es/datasets/contracts_ca/sql"];
const AXE = path.join(__dirname, "..", "node_modules", "axe-core", "axe.min.js");

(async () => {
  const browser = await chromium.launch();
  let failures = 0;
  for (const width of [1280, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    for (const route of PAGES) {
      await page.goto(BASE + route, { waitUntil: "load" });
      // The SQL lab runs its first guided query in the browser: audit the page with results.
      if (route.endsWith("/sql")) await page.waitForSelector("#query-results h3, #query-results [role=note]");
      await page.addScriptTag({ path: AXE });
      const result = await page.evaluate(() =>
        // eslint-disable-next-line no-undef
        axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] }),
      );
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      const lang = await page.evaluate(() => document.documentElement.lang);
      console.log(`${width}px ${route} lang=${lang} violations=${result.violations.length}${overflow ? " HORIZONTAL-OVERFLOW" : ""}`);
      for (const v of result.violations) {
        console.log(`  [${v.impact}] ${v.id}: ${v.help}`);
        for (const n of v.nodes.slice(0, 5)) console.log(`     ${n.target.join(" ")} — ${n.failureSummary.split("\n")[1] ?? ""}`);
      }
      failures += result.violations.length + (overflow ? 1 : 0);
    }
    await page.close();
  }
  await browser.close();
  process.exit(failures ? 1 : 0);
})();
