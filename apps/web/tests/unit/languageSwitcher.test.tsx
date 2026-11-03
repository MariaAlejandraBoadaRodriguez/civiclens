import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderIn } from "./render";

vi.mock("@/i18n/routing", () => ({
  routing: { locales: ["en", "es"] },
  usePathname: () => "/datasets/secop_co",
  Link: ({ children, locale, hrefLang: _h, ...props }: Record<string, unknown> & { children: unknown; locale: string }) => (
    <a href={`/${locale}`} {...props}>
      {children as never}
    </a>
  ),
}));

describe("LanguageSwitcher", () => {
  it("names each link starting with its visible code (WCAG 2.5.3, axe label-content-name-mismatch)", async () => {
    const { LanguageSwitcher } = await import("@/components/layout/LanguageSwitcher");
    renderIn("es", <LanguageSwitcher />);
    const en = screen.getByRole("link", { name: /^en\s+English$/i });
    const es = screen.getByRole("link", { name: /^es\s+Español$/i });
    expect(en).not.toHaveAttribute("aria-label");
    expect(es).toHaveAttribute("aria-current", "true");
  });
});
