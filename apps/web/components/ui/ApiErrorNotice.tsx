"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import type { ApiFailure } from "@/lib/apiClient";

/**
 * What the user sees when an API call fails: the API's own localized problem, or — when the
 * engine did not answer (network error, 502 while it restarts) — a translated message. Always
 * with a Retry button when the action can be retried.
 */
export function ApiErrorNotice({ error, onRetry }: { error: ApiFailure; onRetry?: () => void }) {
  const t = useTranslations("common.apiError");
  const title = error.kind === "problem" ? error.problem.title : t("unavailableTitle");
  const detail = error.kind === "problem" ? error.problem.detail : t("unavailableBody");
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-card border border-flag-border bg-flag-tint p-4 text-sm text-flag-text">
      <div className="flex flex-col gap-1">
        <p className="m-0 font-semibold">{title}</p>
        {detail && <p className="m-0 text-text">{detail}</p>}
      </div>
      {onRetry && (
        <div>
          <Button variant="attention" onClick={onRetry}>
            {t("retry")}
          </Button>
        </div>
      )}
    </div>
  );
}
