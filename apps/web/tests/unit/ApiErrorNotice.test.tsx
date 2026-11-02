import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiErrorNotice } from "@/components/ui/ApiErrorNotice";
import { renderIn } from "./render";

describe("ApiErrorNotice", () => {
  it.each([
    ["en", "The engine did not answer", "Retry"],
    ["es", "El motor no respondió", "Reintentar"],
  ] as const)("explains an unavailable engine in %s with a Retry button", (locale, title, retry) => {
    const onRetry = vi.fn();
    renderIn(locale, <ApiErrorNotice error={{ kind: "unavailable", status: 502 }} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(title);
    fireEvent.click(screen.getByRole("button", { name: retry }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows the API's own problem and no Retry when the action cannot be retried", () => {
    const problem = { type: "x", title: "Only read queries are allowed", detail: "DROP is not allowed.", status: 400, code: "sql.forbidden_statement" };
    renderIn("en", <ApiErrorNotice error={{ kind: "problem", problem }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Only read queries are allowed");
    expect(screen.getByRole("alert")).toHaveTextContent("DROP is not allowed.");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
