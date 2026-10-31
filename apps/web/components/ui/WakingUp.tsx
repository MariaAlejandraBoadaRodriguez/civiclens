"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { useRouter } from "@/i18n/routing";

/**
 * Cold-start state for the free-tier API (ROADMAP §2: Render cold start ~30–60 s).
 * Re-renders the server page every `refreshSeconds` until the API answers; after
 * `timeoutSeconds` it stops and shows an error with a Retry button — it never spins forever.
 * `live={false}` renders the static state only (design system page).
 */
export function WakingUp({
  refreshSeconds = 5,
  timeoutSeconds = 90,
  live = true,
}: {
  refreshSeconds?: number;
  timeoutSeconds?: number;
  live?: boolean;
}) {
  const t = useTranslations("common.wakingUp");
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    if (!live) return;
    const started = Date.now();
    const id = setInterval(() => {
      if (Date.now() - started >= timeoutSeconds * 1000) {
        clearInterval(id);
        setGaveUp(true);
      } else {
        router.refresh();
      }
    }, refreshSeconds * 1000);
    return () => clearInterval(id);
  }, [live, attempt, refreshSeconds, timeoutSeconds, router]);

  const retry = useCallback(() => {
    setGaveUp(false);
    setAttempt((n) => n + 1);
    router.refresh();
  }, [router]);

  if (gaveUp) {
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-card border border-flag-border bg-flag-tint p-5 text-flag-text"
      >
        <div className="flex flex-col gap-1">
          <p className="m-0 text-[15px] font-semibold">{t("failedTitle")}</p>
          <p className="m-0 text-sm text-text">{t("failedBody", { seconds: timeoutSeconds })}</p>
        </div>
        <div>
          <Button variant="attention" onClick={retry}>
            {t("retry")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-4 rounded-card border border-primary-border bg-primary-soft p-5 text-primary-dark"
    >
      <span
        aria-hidden="true"
        className="mt-0.5 h-6 w-6 shrink-0 animate-spin rounded-full border-[3px] border-primary-border border-t-primary"
      />
      <div className="flex flex-col gap-1">
        <p className="m-0 text-[15px] font-semibold">{t("title")}</p>
        <p className="m-0 text-sm text-text">{t("body")}</p>
      </div>
    </div>
  );
}
