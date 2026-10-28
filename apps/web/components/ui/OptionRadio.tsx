"use client";

import * as RadioGroup from "@radix-ui/react-radio-group";
import { useId } from "react";

export type RadioOption = { value: string; label: string; hint?: string; disabled?: boolean };

/** Radio list with hints (Cleaning studio "Choose how to unify"). Radix = keyboard + ARIA. */
export function OptionRadio({
  legend,
  options,
  value,
  defaultValue,
  onValueChange,
  name,
}: {
  legend: string;
  options: RadioOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  name?: string;
}) {
  const legendId = useId();
  const base = useId();
  return (
    <div className="flex flex-col gap-2.5 rounded-panel border border-line p-4">
      <span id={legendId} className="px-1.5 text-sm font-medium text-ink">
        {legend}
      </span>
      <RadioGroup.Root
        aria-labelledby={legendId}
        value={value}
        defaultValue={defaultValue}
        onValueChange={onValueChange}
        name={name}
        className="flex flex-col gap-1"
      >
        {options.map((opt) => {
          const id = `${base}-${opt.value}`;
          return (
            <label
              key={opt.value}
              htmlFor={id}
              className="flex min-h-touch cursor-pointer items-start gap-2.5 rounded-control p-2 text-[15px] hover:bg-ground has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60 has-[[data-state=checked]]:bg-primary-soft"
            >
              <RadioGroup.Item
                id={id}
                value={opt.value}
                disabled={opt.disabled}
                aria-describedby={opt.hint ? `${id}-hint` : undefined}
                className="mt-1 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border-2 border-muted bg-surface hover:border-primary data-[state=checked]:border-primary disabled:border-line-strong"
              >
                <RadioGroup.Indicator className="h-2 w-2 rounded-full bg-primary" />
              </RadioGroup.Item>
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{opt.label}</span>
                {opt.hint && (
                  <span id={`${id}-hint`} className="text-[13px] text-muted">
                    {opt.hint}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </RadioGroup.Root>
    </div>
  );
}
