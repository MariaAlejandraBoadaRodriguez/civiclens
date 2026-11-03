import { unstable_noStore as noStore } from "next/cache";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { KeyConsole } from "@/components/admin/KeyConsole";
import { SignInButtons, SignOutButton } from "@/components/admin/SignIn";
import { Card } from "@/components/ui/Card";
import { WakingUp } from "@/components/ui/WakingUp";
import { adminConfig } from "@/lib/admin/access";
import { adminLogin } from "@/lib/admin/auth";
import type { ApiKey } from "@/lib/api-types";

export const dynamic = "force-dynamic";

type Props = { params: { locale: string }; searchParams: { error?: string } };

export async function generateMetadata({ params: { locale } }: Props) {
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("metaTitle"), robots: { index: false } };
}

const SERVER_API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function listKeys(login: string, locale: string): Promise<ApiKey[] | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/api/v1/keys`, {
      headers: {
        Authorization: `Bearer ${process.env.ADMIN_API_TOKEN}`,
        "X-Admin-Login": login,
        "Accept-Language": locale,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
    return res.ok ? ((await res.json()) as { items: ApiKey[] }).items : null;
  } catch {
    return null;
  }
}

export default async function AdminPage({ params: { locale }, searchParams }: Props) {
  noStore(); // per request: the session cookie decides what is shown
  setRequestLocale(locale);
  const t = await getTranslations("admin");
  const config = adminConfig();
  const login = config.ready ? await adminLogin() : null;
  const keys = login ? await listKeys(login, locale) : null;

  return (
    <main id="main" className="mx-auto flex max-w-container flex-col gap-6 px-6 pb-12 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
          <p className="m-0 text-base text-muted">{t("subtitle")}</p>
        </div>
        {login && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted">{t("signedInAs", { login })}</span>
            <SignOutButton />
          </div>
        )}
      </div>

      {!config.ready && (
        <Card title={t("notConfigured.title")} titleId="admin-not-configured" className="max-w-xl">
          <p className="m-0 text-[15px]">{t("notConfigured.body")}</p>
          <p className="m-0 break-words font-mono text-xs text-muted">{config.missing.join(", ")}</p>
        </Card>
      )}

      {config.ready && !login && (
        <Card title={t("signIn.title")} titleId="admin-sign-in" className="max-w-xl">
          {searchParams.error && (
            <div role="alert" className="rounded-card border border-flag-border bg-flag-tint p-4 text-sm text-flag-text">
              {searchParams.error === "AccessDenied" ? t("signIn.denied") : t("signIn.failed")}
            </div>
          )}
          <p className="m-0 text-[15px]">{t("signIn.body")}</p>
          <SignInButtons providers={config.providers} />
        </Card>
      )}

      {login && keys === null && <WakingUp />}
      {login && keys !== null && <KeyConsole initial={keys} />}
    </main>
  );
}
