import { useId } from "react";
import { cn } from "@/lib/cn";

/** Score at or above this is "good" (blue); below needs attention (orange). */
export const SCORE_THRESHOLD = 70;

export function ScoreBar({
  label,
  value,
  max = 100,
  display,
  height = "md",
}: {
  label: string;
  value: number;
  max?: number;
  /** Already-localized value text; defaults to the raw number. */
  display?: string;
  height?: "sm" | "md";
}) {
  const id = useId();
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const good = pct >= SCORE_THRESHOLD;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between gap-3 text-sm">
        <span id={id}>{label}</span>
        <span className="font-mono">{display ?? value}</span>
      </div>
      <div
        role="meter"
        aria-labelledby={id}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={display}
        className={cn("rounded bg-track", height === "md" ? "h-2" : "h-1.5")}
      >
        <div
          className={cn("h-full rounded", good ? "bg-primary" : "bg-flag")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
