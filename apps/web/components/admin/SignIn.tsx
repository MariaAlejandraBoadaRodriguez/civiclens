"use client";

import { signIn, signOut } from "next-auth/react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";

export function SignInButtons({ providers }: { providers: ("github" | "test-admin")[] }) {
  const t = useTranslations("admin.signIn");
  const locale = useLocale();
  const callbackUrl = `/${locale}/admin`;
  return (
    <div className="flex flex-wrap gap-3">
      {providers.includes("github") && (
        <Button onClick={() => void signIn("github", { callbackUrl })}>{t("github")}</Button>
      )}
      {providers.includes("test-admin") && (
        <Button variant="secondary" onClick={() => void signIn("test-admin", { callbackUrl })}>
          {t("testMode")}
        </Button>
      )}
    </div>
  );
}

export function SignOutButton() {
  const t = useTranslations("admin");
  const locale = useLocale();
  return (
    <Button variant="secondary" onClick={() => void signOut({ callbackUrl: `/${locale}/admin` })}>
      {t("signOut")}
    </Button>
  );
}
