import { test as base, expect, type Page } from "@playwright/test";
import en from "../messages/en.json";
import es from "../messages/es.json";

export const MESSAGES = { en, es } as const;
export type Lang = keyof typeof MESSAGES;

export type Console = {
  /** Declare a console error the journey provokes on purpose (e.g. a rejected SQL query: the
   * browser logs every 4xx response). Anything not declared fails the test. */
  allow: (pattern: RegExp) => void;
};

/** Every journey fails on any browser console error, uncaught page error or 5xx response. */
export const test = base.extend<{ browserConsole: Console }>({
  browserConsole: [
    async ({ page }, use) => {
      const errors: string[] = [];
      const allowed: RegExp[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") errors.push(`console: ${msg.text()} @ ${msg.location().url}`);
      });
      page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
      page.on("response", (res) => {
        if (res.status() >= 500) errors.push(`HTTP ${res.status()} ${res.url()}`);
      });
      await use({ allow: (pattern) => allowed.push(pattern) });
      const unexpected = errors.filter((e) => !allowed.some((re) => re.test(e)));
      expect(unexpected, "browser console errors / 5xx responses").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Wait for `done`, pressing the visible Retry button when the API rate limit (30 heavy calls
 * per minute for anonymous callers, as in production) answers 429 — what a user would do.
 * The 429 the browser logs is declared, so only that console error is tolerated.
 */
export async function withRetry(
  page: Page,
  browserConsole: Console,
  retryLabel: string,
  done: () => Promise<boolean>,
  attempts = 8,
): Promise<void> {
  browserConsole.allow(/status of 429/);
  for (let n = 0; n < attempts; n += 1) {
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      if (await done()) return;
      await page.waitForTimeout(500);
    }
    const retry = page.getByRole("button", { name: retryLabel }).first();
    if (await retry.isVisible()) {
      await page.waitForTimeout(10_000); // the limit window is one minute
      await retry.click();
    }
  }
  expect(await done(), "still not done after waiting out the rate limit").toBe(true);
}
