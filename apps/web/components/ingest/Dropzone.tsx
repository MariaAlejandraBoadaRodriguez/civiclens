"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { ProgressBar } from "@/components/ui/ProgressBar";
import type { Dataset, Job } from "@/lib/api-types";
import { uploadWithProgress, waitForJob, type ApiFailure } from "@/lib/apiClient";
import { cn } from "@/lib/cn";

type State =
  | { step: "idle" }
  | { step: "uploading"; name: string; percent: number }
  | { step: "processing"; name: string; percent: number; label: string | null }
  | { step: "error"; error: ApiFailure; file?: File };

const MAX_MB = 50;

/** Upload a CSV / XLSX / JSON file, wait for the ingest job, then open its profile. */
export function Dropzone() {
  const t = useTranslations("ingest.upload");
  const locale = useLocale();
  const router = useRouter();
  const inputId = useId();
  const statusId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<State>({ step: "idle" });
  const [over, setOver] = useState(false);
  const busy = state.step === "uploading" || state.step === "processing";

  async function send(file: File) {
    if (file.size > MAX_MB * 1024 * 1024) {
      const problem = {
        type: "",
        status: 413,
        code: "ingest.too_large",
        title: t("tooLargeTitle"),
        detail: t("tooLargeDetail", { mb: MAX_MB }),
      };
      setState({ step: "error", error: { kind: "problem", problem } });
      return;
    }
    setState({ step: "uploading", name: file.name, percent: 0 });
    const body = new FormData();
    body.append("file", file);
    const accepted = await uploadWithProgress<{ dataset: Dataset; job: Pick<Job, "id" | "status"> }>(
      "/api/v1/datasets",
      body,
      locale,
      (percent) => setState({ step: "uploading", name: file.name, percent }),
    );
    if (!accepted.ok) {
      setState({ step: "error", error: accepted.error, file });
      return;
    }
    setState({ step: "processing", name: file.name, percent: 0, label: null });
    const job = await waitForJob(accepted.data.job.id, locale, {
      onProgress: (j) =>
        setState({ step: "processing", name: file.name, percent: j.progress ?? 0, label: j.phase_label ?? null }),
    });
    if (!job.ok) {
      // A file the engine could not read is final; a lost connection can be retried.
      setState({ step: "error", error: job.error, file: job.error.kind === "unavailable" ? file : undefined });
      return;
    }
    // The profile page shows the success banner (?ready=1) and takes focus.
    router.push(`/datasets/${accepted.data.dataset.id}?ready=1`);
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && !busy) void send(file);
  }

  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        aria-describedby={statusId}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-panel border-2 border-dashed p-6 text-center transition-colors",
          over ? "border-primary bg-primary-soft" : "border-line-dropzone hover:border-primary",
          busy && "cursor-wait opacity-80",
        )}
      >
        <svg aria-hidden="true" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-primary">
          <path d="M12 16V4M7 9l5-5 5 5" />
          <path d="M4 16v4h16v-4" />
        </svg>
        <span className="text-[15px] font-medium text-ink">{t("cta")}</span>
        <span className="text-[13px] text-muted">{t("hint", { mb: MAX_MB })}</span>
        <input
          ref={input}
          id={inputId}
          type="file"
          accept=".csv,.txt,.xlsx,.json,text/csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={busy}
          className="max-w-full text-[13px] file:mr-3 file:min-h-touch file:rounded-control file:border file:border-line-strong file:bg-surface file:px-3 file:text-ink"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void send(file);
          }}
        />
      </label>
      <div id={statusId} aria-live="polite" className="min-h-5 text-[13px]">
        {state.step === "uploading" && (
          <ProgressBar label={t("uploading", { name: state.name })} value={state.percent} detail={t("uploadingDetail")} />
        )}
        {state.step === "processing" && (
          <ProgressBar
            label={t("processing", { name: state.name })}
            value={state.percent}
            detail={state.label ?? t("processingDetail")}
          />
        )}
      </div>
      {state.step === "error" && (
        <ApiErrorNotice error={state.error} onRetry={state.file ? () => void send(state.file as File) : undefined} />
      )}
    </div>
  );
}
