import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderIn } from "./render";

vi.mock("@/i18n/routing", () => ({ Link: ({ children }: { children: unknown }) => children }));

describe("error page", () => {
  it("explains the failure in Spanish and retries", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { default: ErrorPage } = await import("@/app/[locale]/error");
    const reset = vi.fn();
    renderIn("es", <ErrorPage error={new Error("boom")} reset={reset} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Algo salió mal en esta página");
    fireEvent.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});
