"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Button, ButtonLink } from "@/components/ui/Button";

/** Any unexpected rendering error: a translated message with Retry, never a blank page. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("common.errorPage");
  useEffect(() => {
    console.warn("render error", error.digest ?? error.message);
  }, [error]);
  return (
    <main id="main" className="mx-auto flex max-w-container flex-col items-start gap-4 px-6 pb-12 pt-12">
      <h1 className="m-0 text-[30px] font-semibold text-ink">{t("title")}</h1>
      <p className="m-0 max-w-xl text-base text-muted">{t("body")}</p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={reset}>{t("retry")}</Button>
        <ButtonLink href="/" variant="secondary">
          {t("home")}
        </ButtonLink>
      </div>
    </main>
  );
}
