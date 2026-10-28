"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { PUBLIC_API_URL } from "@/lib/api";
import type { Job, Problem } from "@/lib/api-types";
import { cn } from "@/lib/cn";

type State =
  | { step: "idle" }
  | { step: "uploading" | "processing"; name: string }
  | { step: "error"; problem: Pick<Problem, "title" | "detail"> };

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
      setState({ step: "error", problem: { title: t("tooLargeTitle"), detail: t("tooLargeDetail", { mb: MAX_MB }) } });
      return;
    }
    setState({ step: "uploading", name: file.name });
    const headers = { "Accept-Language": locale };
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/datasets`, { method: "POST", body, headers });
      const json = await res.json();
      if (!res.ok) {
        setState({ step: "error", problem: json as Problem });
        return;
      }
      setState({ step: "processing", name: file.name });
      const jobUrl = `${PUBLIC_API_URL}/api/v1/jobs/${json.job.id}`;
      for (let i = 0; i < 120; i += 1) {
        const job = (await (await fetch(jobUrl, { headers })).json()) as Job;
        if (job.status === "succeeded") {
          router.push(`/datasets/${json.dataset.id}`);
          return;
        }
        if (job.status === "failed") {
          setState({ step: "error", problem: job.error ?? { title: t("failedTitle"), detail: "" } });
          return;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      setState({ step: "error", problem: { title: t("failedTitle"), detail: t("timeout") } });
    } catch {
      setState({ step: "error", problem: { title: t("networkTitle"), detail: t("networkDetail") } });
    }
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
      <div id={statusId} role="status" aria-live="polite" className="min-h-5 text-[13px]">
        {state.step === "uploading" && <span className="text-muted">{t("uploading", { name: state.name })}</span>}
        {state.step === "processing" && <span className="text-muted">{t("processing", { name: state.name })}</span>}
        {state.step === "error" && (
          <span className="flex flex-col text-flag-text">
            <strong className="font-semibold">{state.problem.title}</strong>
            {state.problem.detail && <span>{state.problem.detail}</span>}
          </span>
        )}
      </div>
    </div>
  );
}
