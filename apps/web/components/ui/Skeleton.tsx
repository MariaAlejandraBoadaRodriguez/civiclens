import { useTranslations } from "next-intl";
import { cn } from "@/lib/cn";

/** Placeholder block shown while data loads. Decorative; pair with SkeletonGroup for a11y. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-control bg-track", className)} />;
}

/** A busy region with N skeleton lines and a screen-reader "Loading…" label. */
export function SkeletonGroup({ lines = 3, className }: { lines?: number; className?: string }) {
  const t = useTranslations("common");
  return (
    <div role="status" aria-busy="true" className={cn("flex flex-col gap-3", className)}>
      <span className="sr-only">{t("loading")}</span>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn("h-4", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}
