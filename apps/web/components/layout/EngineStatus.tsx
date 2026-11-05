"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { PUBLIC_API_URL } from "@/lib/api";

type State = "checking" | "starting" | "ready" | "failed";

/**
 * Landing-page engine check. The free API host sleeps when idle; a cron keeps it warm during
 * the day, but a visitor may still arrive to a sleeping engine. Quiet while /health answers
 * fast; after `slowMs` it says the engine is starting (30–60 s) and keeps polling; it never
 * spins forever: after `timeoutMs` it offers a retry.
 */
export function EngineStatus({
  slowMs = 2000,
  pollMs = 4000,
  timeoutMs = 120_000,
}: {
  slowMs?: number;
  pollMs?: number;
  timeoutMs?: number;
}) {
  const t = useTranslations("landing.engine");
  const [state, setState] = useState<State>("checking");
  const [attempt, setAttempt] = useState(0);
  const done = useRef(false);

  useEffect(() => {
    done.current = false;
    const started = Date.now();
    const slow = setTimeout(() => {
      if (!done.current) setState("starting");
    }, slowMs);
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function ping() {
      try {
        const res = await fetch(`${PUBLIC_API_URL}/health`, { cache: "no-store" });
        if (res.ok) {
          done.current = true;
          setState("ready");
          return;
        }
      } catch {
        /* sleeping or restarting: try again below */
      }
      if (Date.now() - started >= timeoutMs) {
        done.current = true;
        setState("failed");
        return;
      }
      timer = setTimeout(() => void ping(), pollMs);
    }
    void ping();
    return () => {
      done.current = true;
      clearTimeout(slow);
      if (timer) clearTimeout(timer);
    };
  }, [attempt, slowMs, pollMs, timeoutMs]);

  const retry = useCallback(() => {
    setState("checking");
    setAttempt((n) => n + 1);
  }, []);

  if (state === "checking") return null;
  if (state === "ready") {
    return (
      <p role="status" className="m-0 flex items-center gap-2 text-sm text-muted" data-testid="engine-ready">
        <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-success" />
        {t("ready")}
      </p>
    );
  }
  if (state === "failed") {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 rounded-card border border-flag-border bg-flag-tint p-4 text-flag-text">
        <p className="m-0 text-sm">{t("failed")}</p>
        <Button variant="attention" onClick={retry}>
          {t("retry")}
        </Button>
      </div>
    );
  }
  return (
    <div role="status" aria-live="polite" data-testid="engine-starting" className="flex items-start gap-3 rounded-card border border-primary-border bg-primary-soft p-4 text-primary-dark">
      <span aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 animate-spin rounded-full border-[3px] border-primary-border border-t-primary" />
      <div className="flex flex-col gap-0.5">
        <p className="m-0 text-[15px] font-semibold">{t("startingTitle")}</p>
        <p className="m-0 text-sm text-text">{t("startingBody")}</p>
      </div>
    </div>
  );
}
