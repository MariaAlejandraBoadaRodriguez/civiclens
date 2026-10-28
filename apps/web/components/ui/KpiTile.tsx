import { cn } from "@/lib/cn";

export type KpiTone = "positive" | "attention" | "neutral";

const tones: Record<KpiTone, string> = {
  positive: "text-success",
  attention: "text-flag",
  neutral: "text-muted",
};

/** Dashboard KPI tile. All texts arrive already localized/formatted. */
export function KpiTile({
  label,
  value,
  note,
  tone = "neutral",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: KpiTone;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-card border border-line bg-surface p-4">
      <span className="text-[13px] text-muted">{label}</span>
      <span className="break-words text-[26px] font-semibold leading-tight text-ink">{value}</span>
      {note && <span className={cn("text-[13px]", tones[tone])}>{note}</span>}
    </div>
  );
}
