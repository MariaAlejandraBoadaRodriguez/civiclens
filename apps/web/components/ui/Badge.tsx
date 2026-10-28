import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeVariant = "language" | "format" | "flag" | "success" | "info";

const variants: Record<BadgeVariant, string> = {
  language: "bg-primary-tint text-primary-dark font-mono",
  format: "bg-subtle text-neutral font-mono",
  flag: "bg-flag-tint text-flag-text",
  success: "bg-success-tint text-success-text",
  info: "bg-primary-tint text-primary-dark",
};

export function Badge({
  variant = "format",
  children,
  className,
}: {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-chip px-2 py-1 text-xs leading-none",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
