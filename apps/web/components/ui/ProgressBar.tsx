import { cn } from "@/lib/cn";

/** Determinate progress (upload %, then the job's server phases). Announced by its label. */
export function ProgressBar({
  label,
  value,
  detail,
  className,
}: {
  label: string;
  value: number;
  detail?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="font-mono text-muted" aria-hidden="true">
          {pct}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={detail ?? `${pct}%`}
        className="h-2.5 overflow-hidden rounded-[3px] bg-subtle"
      >
        <div className="h-full rounded-[3px] bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      {detail && <span className="text-[13px] text-muted">{detail}</span>}
    </div>
  );
}
