"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type TabItem = {
  value: string;
  label: string;
  content: ReactNode;
  /** "later" tabs (mockup ML lab): dashed border, not selectable. */
  disabled?: boolean;
};

const triggerStyles = {
  light:
    "min-h-touch rounded-control border border-line-strong bg-surface px-4 py-3 text-[15px] text-ink hover:border-ink " +
    "data-[state=active]:border-ink data-[state=active]:bg-ink data-[state=active]:font-medium data-[state=active]:text-white " +
    "disabled:cursor-not-allowed disabled:border-dashed disabled:text-muted disabled:hover:border-line-strong",
  dark:
    "min-h-touch rounded-nav border border-ink-line px-3 text-[13px] text-ink-text hover:border-ink-text hover:text-white " +
    "data-[state=active]:border-ink-raised data-[state=active]:bg-ink-raised data-[state=active]:text-white " +
    "disabled:cursor-not-allowed disabled:opacity-60",
};

/** Accessible tabs (Radix): arrow-key navigation, roles and aria-selected handled. */
export function Tabs({
  label,
  items,
  defaultValue,
  variant = "light",
}: {
  label: string;
  items: TabItem[];
  defaultValue?: string;
  variant?: "light" | "dark";
}) {
  return (
    <RadixTabs.Root
      defaultValue={defaultValue ?? items.find((i) => !i.disabled)?.value}
      className={cn("flex flex-col gap-4", variant === "dark" && "focus-on-dark")}
    >
      <RadixTabs.List aria-label={label} className={cn("flex flex-wrap", variant === "light" ? "gap-2" : "gap-1.5")}>
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            disabled={item.disabled}
            className={triggerStyles[variant]}
          >
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className="min-w-0">
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
