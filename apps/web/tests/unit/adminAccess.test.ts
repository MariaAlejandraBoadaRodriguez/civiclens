import { describe, expect, it } from "vitest";
import { adminConfig, isAllowedLogin, testLoginEnabled } from "@/lib/admin/access";

const full = {
  NEXTAUTH_SECRET: "s",
  ADMIN_GITHUB_LOGIN: "OwnerLogin",
  ADMIN_API_TOKEN: "t",
  GITHUB_ID: "id",
  GITHUB_SECRET: "secret",
};

describe("admin access", () => {
  it("allows only the allowlisted GitHub login, case-insensitively", () => {
    expect(isAllowedLogin("ownerlogin", full)).toBe(true);
    expect(isAllowedLogin("someone-else", full)).toBe(false);
    expect(isAllowedLogin(null, full)).toBe(false);
    expect(isAllowedLogin("", { ...full, ADMIN_GITHUB_LOGIN: "" })).toBe(false);
    expect(isAllowedLogin("anyone", {})).toBe(false); // nobody when no allowlist is set
  });

  it("never enables the test sign-in on Vercel", () => {
    expect(testLoginEnabled({ ADMIN_TEST_LOGIN: "true" })).toBe(true);
    expect(testLoginEnabled({ ADMIN_TEST_LOGIN: "true", VERCEL: "1" })).toBe(false);
    expect(testLoginEnabled({})).toBe(false);
  });

  it("lists what is missing instead of failing", () => {
    expect(adminConfig(full)).toEqual({ ready: true, providers: ["github"] });
    expect(adminConfig({})).toEqual({
      ready: false,
      missing: ["NEXTAUTH_SECRET", "ADMIN_GITHUB_LOGIN", "ADMIN_API_TOKEN", "GITHUB_ID / GITHUB_SECRET"],
    });
    const test = { ...full, GITHUB_ID: "", ADMIN_TEST_LOGIN: "true" };
    expect(adminConfig(test)).toEqual({ ready: true, providers: ["test-admin"] });
  });
});
