"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/cn";

/** Dark code block (recipe export, SQL editor preview, API curl example). Code is never translated. */
export function CodeBlock({
  code,
  label,
  copyable = true,
  className,
}: {
  code: string;
  /** Accessible name of the code region, e.g. "pandas code". */
  label: string;
  copyable?: boolean;
  className?: string;
}) {
  const t = useTranslations("common");
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className={cn("focus-on-dark flex flex-col rounded-control bg-code", className)}>
      {copyable && (
        <div className="flex justify-end border-b border-ink-line px-2 py-1">
          <button
            type="button"
            onClick={copy}
            className="min-h-touch rounded-nav px-3 text-[13px] text-ink-text hover:bg-ink-raised hover:text-white"
          >
            <span aria-live="polite">{copied ? t("copied") : t("copy")}</span>
          </button>
        </div>
      )}
      <pre
        tabIndex={0}
        aria-label={label}
        className="m-0 overflow-x-auto whitespace-pre p-4 font-mono text-[13px] leading-relaxed text-code-text"
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}
