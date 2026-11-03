import { getServerSession, type NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GitHubProvider from "next-auth/providers/github";
import { adminConfig, isAllowedLogin, testLoginEnabled } from "./access";

/**
 * Auth.js (GitHub OAuth) for the one allowlisted admin. The session is a signed, HttpOnly JWT
 * cookie; the API's admin token never reaches the browser — the console calls this app's
 * route handlers, which add it server-side.
 */
function providers(): NextAuthOptions["providers"] {
  const list: NextAuthOptions["providers"] = [];
  if (process.env.GITHUB_ID && process.env.GITHUB_SECRET) {
    list.push(
      GitHubProvider({ clientId: process.env.GITHUB_ID, clientSecret: process.env.GITHUB_SECRET }),
    );
  }
  if (testLoginEnabled()) {
    list.push(
      CredentialsProvider({
        id: "test-admin",
        name: "Test admin",
        credentials: {},
        authorize: () => {
          const login = process.env.ADMIN_GITHUB_LOGIN ?? "";
          return { id: login, name: login };
        },
      }),
    );
  }
  return list;
}

export const authOptions: NextAuthOptions = {
  providers: providers(),
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  // Our own, translated page instead of Auth.js's English-only screens; the locale
  // middleware sends /admin to /en/admin or /es/admin.
  pages: { signIn: "/admin", error: "/admin" },
  callbacks: {
    signIn({ account, profile, user }) {
      const login =
        account?.provider === "github" ? (profile as { login?: string } | undefined)?.login : user.name;
      return isAllowedLogin(login);
    },
    jwt({ token, account, profile, user }) {
      if (account?.provider === "github") token.login = (profile as { login?: string }).login;
      else if (account) token.login = user.name ?? undefined;
      return token;
    },
    session({ session, token }) {
      return { ...session, login: typeof token.login === "string" ? token.login : null };
    },
  },
};

/** The signed-in admin's GitHub login, or null (signed out, not allowlisted, not configured). */
export async function adminLogin(): Promise<string | null> {
  if (!adminConfig().ready) return null;
  const session = (await getServerSession(authOptions)) as { login?: string | null } | null;
  return session?.login && isAllowedLogin(session.login) ? session.login : null;
}
