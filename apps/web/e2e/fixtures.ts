import { test as base, expect } from "@playwright/test";
import en from "../messages/en.json";
import es from "../messages/es.json";

export const MESSAGES = { en, es } as const;
export type Lang = keyof typeof MESSAGES;

type Console = {
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
