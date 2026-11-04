"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import type { Dataset, Job } from "@/lib/api-types";
import { uploadWithProgress, waitForJob, type ApiFailure } from "@/lib/apiClient";

/** Public sample that is not procurement data (South German Credit, CC BY 4.0), served by the
 * web app and uploaded like any user file: the whole pipeline on "any data" in one click. */
export const ANY_SAMPLE = { path: "/samples/german_credit.csv", name: "german_credit.csv" };

type State =
  | { step: "idle" }
  | { step: "working"; percent: number; label: string }
  | { step: "error"; error: ApiFailure };

export function TryAnyData() {
  const t = useTranslations("landing.samples.anyData");
  const locale = useLocale();
  const router = useRouter();
  const [state, setState] = useState<State>({ step: "idle" });

  async function start() {
    setState({ step: "working", percent: 2, label: t("loading") });
    let file: File;
    try {
      const res = await fetch(ANY_SAMPLE.path);
      file = new File([await res.blob()], ANY_SAMPLE.name, { type: "text/csv" });
    } catch {
      setState({ step: "error", error: { kind: "unavailable" } });
      return;
    }
    const body = new FormData();
    body.append("file", file);
    const accepted = await uploadWithProgress<{ dataset: Dataset; job: Pick<Job, "id" | "status"> }>(
      "/api/v1/datasets",
      body,
      locale,
      (percent) => setState({ step: "working", percent: percent / 4, label: t("uploading") }),
    );
    if (!accepted.ok) return setState({ step: "error", error: accepted.error });
    const job = await waitForJob(accepted.data.job.id, locale, {
      onProgress: (j) => setState({ step: "working", percent: 25 + (j.progress ?? 0) * 0.75, label: j.phase_label ?? t("loading") }),
    });
    if (!job.ok) return setState({ step: "error", error: job.error });
    router.push(`/datasets/${accepted.data.dataset.id}?ready=1`);
  }

  return (
    <div className="mt-auto flex flex-col gap-3">
      <Button onClick={() => void start()} disabled={state.step === "working"} data-testid="try-any-data">
        {state.step === "working" ? t("loading") : t("button")}
      </Button>
      {state.step === "working" && <ProgressBar value={state.percent} label={state.label} />}
      {state.step === "error" && <ApiErrorNotice error={state.error} onRetry={() => void start()} />}
    </div>
  );
}
