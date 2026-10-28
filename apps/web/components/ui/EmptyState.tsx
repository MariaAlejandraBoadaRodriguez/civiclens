import type { ReactNode } from "react";

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
      <span aria-hidden="true" className="text-primary">
        {icon ?? (
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 7h16M4 12h10M4 17h6" />
          </svg>
        )}
      </span>
      <h3 className="m-0 text-lg font-semibold text-ink">{title}</h3>
      {body && <p className="m-0 max-w-md text-[15px] text-muted">{body}</p>}
      {action}
    </div>
  );
}
