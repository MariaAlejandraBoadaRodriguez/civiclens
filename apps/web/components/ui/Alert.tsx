import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type AlertProps = {
  variant?: "warning" | "pii" | "info";
  title?: ReactNode;
  titleId?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
};

const variants = {
  warning: "bg-flag-tint text-flag-text",
  pii: "border border-flag-border bg-flag-tint text-flag-text",
  info: "border border-primary-border bg-primary-soft text-primary-dark",
};

/**
 * Inline message. `pii` is the "Personal data detected" card (Ingest screen);
 * `warning` is the model-card note ("leads, not accusations").
 */
export function Alert({ variant = "warning", title, titleId, children, actions, className }: AlertProps) {
  return (
    <div
      role={variant === "pii" ? "alert" : "note"}
      aria-labelledby={title && titleId ? titleId : undefined}
      className={cn(
        "flex flex-col gap-3 rounded-card p-4 text-sm leading-relaxed",
        variant === "pii" && "p-[22px] text-[15px]",
        variants[variant],
        className,
      )}
    >
      {title && (
        <h3 id={titleId} className="m-0 text-lg font-semibold">
          {title}
        </h3>
      )}
      <div className="flex flex-col gap-2">{children}</div>
      {actions && <div className="mt-auto flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  );
}
