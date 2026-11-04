"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Large result banner: green when a step finished, red when it failed. It is a live region
 * (status / alert) and takes focus when it appears, so screen readers announce it and keyboard
 * users land on its actions.
 */
export function StatusBanner({
  variant,
  title,
  children,
  actions,
  focusOnMount = true,
}: {
  variant: "success" | "error";
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  focusOnMount?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focusOnMount) ref.current?.focus();
  }, [focusOnMount]);
  const success = variant === "success";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role={success ? "status" : "alert"}
      data-testid={`banner-${variant}`}
      className={cn(
        "flex flex-col gap-3 rounded-card border-2 p-5 outline-none focus-visible:ring-2 focus-visible:ring-primary",
        success ? "border-success bg-success-tint text-success-text" : "border-flag-border bg-flag-tint text-flag-text",
      )}
    >
      <div className="flex items-start gap-3">
        <svg aria-hidden="true" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="mt-0.5 shrink-0">
          {success ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M12 7v6M12 17h.01M10.3 3.9L2.6 17.5A2 2 0 004.3 20.5h15.4a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />}
        </svg>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="m-0 text-lg font-semibold">{title}</p>
          {children && <div className="text-[15px] text-text">{children}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  );
}
