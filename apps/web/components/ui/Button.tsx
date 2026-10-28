import type { ButtonHTMLAttributes, ComponentProps, ReactNode } from "react";
import { Link } from "@/i18n/routing";
import { cn } from "@/lib/cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "attention"
  | "attentionOutline"
  | "inverse";

const base =
  "inline-flex min-h-touch items-center justify-center gap-2 rounded-control px-5 py-3 text-[15px] font-medium leading-tight no-underline transition-colors " +
  "disabled:cursor-not-allowed aria-disabled:cursor-not-allowed aria-disabled:pointer-events-none";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-white hover:bg-primary-dark hover:text-white disabled:bg-line-strong disabled:text-neutral aria-disabled:bg-line-strong aria-disabled:text-neutral",
  secondary:
    "border border-line-strong bg-surface text-ink hover:border-ink hover:bg-ground hover:text-ink disabled:border-line disabled:bg-subtle disabled:text-muted",
  ghost:
    "bg-transparent px-2 text-primary underline-offset-4 hover:text-primary-dark hover:underline disabled:text-muted disabled:no-underline",
  attention:
    "bg-flag-text text-white hover:bg-flag-hover hover:text-white disabled:bg-line-strong disabled:text-neutral",
  attentionOutline:
    "border border-flag-strong bg-transparent text-flag-text hover:bg-surface hover:text-flag-text disabled:border-line disabled:text-muted",
  inverse: "bg-surface text-ink hover:bg-subtle hover:text-ink disabled:bg-ink-line disabled:text-ink-text",
};

export function buttonClass(variant: ButtonVariant = "primary", className?: string) {
  return cn(base, variants[variant], className);
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

export function Button({ variant = "primary", className, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, className)} {...props} />;
}

type ButtonLinkProps = ComponentProps<typeof Link> & { variant?: ButtonVariant };

/** A link that looks like a button (navigation, e.g. "Continue to cleaning →"). */
export function ButtonLink({ variant = "primary", className, ...props }: ButtonLinkProps) {
  return <Link className={buttonClass(variant, className)} {...props} />;
}
