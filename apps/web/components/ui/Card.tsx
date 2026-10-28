import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type CardProps = HTMLAttributes<HTMLElement> & {
  as?: "section" | "div" | "article" | "aside";
  title?: ReactNode;
  titleId?: string;
  actions?: ReactNode;
  tone?: "default" | "attention" | "dark";
};

const tones = {
  default: "border border-line bg-surface text-text",
  attention: "border border-flag-border bg-flag-tint text-flag-text",
  dark: "focus-on-dark bg-ink text-code-text",
};

const titleTones = { default: "text-ink", attention: "text-flag-text", dark: "text-white" };

export function Card({
  as: Tag = "section",
  title,
  titleId,
  actions,
  tone = "default",
  className,
  children,
  ...props
}: CardProps) {
  return (
    <Tag
      aria-labelledby={title && titleId ? titleId : undefined}
      className={cn("flex min-w-0 flex-col gap-4 rounded-card p-[22px]", tones[tone], className)}
      {...props}
    >
      {(title || actions) && (
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          {title && (
            <h2 id={titleId} className={cn("m-0 text-lg font-semibold", titleTones[tone])}>
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </Tag>
  );
}
