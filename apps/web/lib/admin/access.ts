/**
 * Who may use the admin console (ROADMAP A2: only the owner signs in, to issue API keys).
 * Pure functions, so the rules are unit-tested without a browser or GitHub.
 */

type Env = Record<string, string | undefined>;

/** The single allowlisted GitHub login (case-insensitive, as GitHub logins are). */
export function isAllowedLogin(login: string | null | undefined, env: Env = process.env): boolean {
  const allowed = env.ADMIN_GITHUB_LOGIN?.trim().toLowerCase();
  return Boolean(allowed && login && login.trim().toLowerCase() === allowed);
}

/**
 * A password-less "test admin" sign-in for the E2E journey (no GitHub in CI). Only when
 * explicitly enabled and never on Vercel, whatever the environment variables say.
 */
export function testLoginEnabled(env: Env = process.env): boolean {
  return env.ADMIN_TEST_LOGIN === "true" && !env.VERCEL;
}

export type AdminConfig =
  | { ready: true; providers: ("github" | "test-admin")[] }
  | { ready: false; missing: string[] };

/** What is missing before the console can work; the page says so instead of crashing. */
export function adminConfig(env: Env = process.env): AdminConfig {
  const providers: ("github" | "test-admin")[] = [];
  if (env.GITHUB_ID && env.GITHUB_SECRET) providers.push("github");
  if (testLoginEnabled(env)) providers.push("test-admin");
  const missing = [
    !env.NEXTAUTH_SECRET && "NEXTAUTH_SECRET",
    !env.ADMIN_GITHUB_LOGIN && "ADMIN_GITHUB_LOGIN",
    !env.ADMIN_API_TOKEN && "ADMIN_API_TOKEN",
    providers.length === 0 && "GITHUB_ID / GITHUB_SECRET",
  ].filter((m): m is string => Boolean(m));
  return missing.length ? { ready: false, missing } : { ready: true, providers };
}
