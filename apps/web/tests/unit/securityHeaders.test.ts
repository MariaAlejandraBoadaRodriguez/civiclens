import { describe, expect, it } from "vitest";
import { securityHeaders } from "@/security-headers.mjs";

describe("security headers", () => {
  const headers = Object.fromEntries(securityHeaders("https://civiclens-api.onrender.com/").map((h: { key: string; value: string }) => [h.key, h.value]));

  it("sets CSP, HSTS and anti-framing", () => {
    expect(headers["Strict-Transport-Security"]).toMatch(/^max-age=\d+/);
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
    expect(headers["Content-Security-Policy"]).toContain("object-src 'none'");
  });

  it("lets the browser call the API origin and nothing else outside this site", () => {
    const connect = headers["Content-Security-Policy"].split("; ").find((d: string) => d.startsWith("connect-src"));
    expect(connect).toContain("https://civiclens-api.onrender.com");
    expect(connect).not.toContain("*");
  });
});
