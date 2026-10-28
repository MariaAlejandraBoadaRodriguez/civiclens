import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  align?: "left" | "right";
  mono?: boolean;
};

/**
 * Table with horizontal scroll on narrow screens. The scroll box is focusable so keyboard
 * users can scroll it (axe: scrollable-region-focusable).
 */
export function DataTable<Row>({
  caption,
  columns,
  rows,
  rowKey,
  minWidth = 640,
  captionHidden = false,
}: {
  caption: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string;
  minWidth?: number;
  captionHidden?: boolean;
}) {
  return (
    <div className="relative overflow-x-auto rounded-control" tabIndex={0} role="region" aria-label={caption}>
      <table className="w-full border-collapse text-sm" style={{ minWidth }}>
        <caption className={cn("pb-2 text-left text-sm text-muted", captionHidden && "sr-only")}>
          {caption}
        </caption>
        <thead>
          <tr className="border-b border-line text-left text-muted">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn("px-2 py-2.5 font-medium", c.align === "right" && "text-right")}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-subtle last:border-0 hover:bg-ground">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn("px-2 py-2.5", c.align === "right" && "text-right", c.mono && "font-mono")}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
