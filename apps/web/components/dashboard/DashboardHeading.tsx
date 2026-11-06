import { useTranslations } from "next-intl";

/** Domain packs with their own dashboard heading (government/procurement uses `title`/`subtitle`). */
export const HEADING_PACKS = ["banking", "marketing", "environmental"] as const;

export type HeadingSpec =
  | { kind: "procurement" }
  | { kind: "pack"; pack: (typeof HEADING_PACKS)[number]; name: string }
  | { kind: "generic"; name: string }
  | { kind: "unknown" };

/**
 * Which heading the dashboard shows: procurement only when the procurement dashboard answered,
 * else the dataset's domain pack (confirmed, or the suggestion that applies), else a generic
 * heading with the dataset's own name.
 */
export function headingFor(input: { procurement: boolean; pack?: string | null; name?: string | null }): HeadingSpec {
  if (input.procurement || input.pack === "government") return { kind: "procurement" };
  if (!input.name) return { kind: "unknown" };
  const pack = HEADING_PACKS.find((p) => p === input.pack);
  return pack ? { kind: "pack", pack, name: input.name } : { kind: "generic", name: input.name };
}

export function DashboardHeading({ spec }: { spec: HeadingSpec }) {
  const t = useTranslations("dashboard");
  const [title, subtitle] =
    spec.kind === "procurement"
      ? [t("title"), t("subtitle")]
      : spec.kind === "pack"
        ? [t(`heading.${spec.pack}.title`), t(`heading.${spec.pack}.subtitle`, { name: spec.name })]
        : spec.kind === "generic"
          ? [t("heading.generic.title", { name: spec.name }), t("heading.generic.subtitle")]
          : [t("heading.unknown.title"), t("heading.unknown.subtitle")];
  return (
    <div className="flex min-w-0 flex-col gap-1.5" data-testid="dashboard-heading" data-kind={spec.kind}>
      <h1 className="m-0 text-[30px] font-semibold text-ink">{title}</h1>
      <p className="m-0 text-base text-muted">{subtitle}</p>
    </div>
  );
}
