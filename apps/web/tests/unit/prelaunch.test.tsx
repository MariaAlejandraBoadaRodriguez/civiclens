import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineStatus } from "@/components/layout/EngineStatus";
import { FeedbackButton, feedbackUrl } from "@/components/layout/FeedbackButton";
import { ResponsibleUse } from "@/components/ui/ResponsibleUse";
import { json, renderIn } from "./render";

afterEach(() => vi.useRealTimers());

describe("Feedback button", () => {
  it("opens the GitHub issue form with the page and language pre-filled", () => {
    renderIn("es", <FeedbackButton />);
    const link = screen.getByRole("link", { name: /Danos tu opinión/ });
    const url = new URL(link.getAttribute("href") as string);
    expect(url.pathname).toBe("/MariaAlejandraBoadaRodriguez/civiclens/issues/new");
    expect(url.searchParams.get("template")).toBe("feedback.yml");
    expect(url.searchParams.get("language")).toBe("es");
    expect(url.searchParams.get("page")).toBe("/es");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("encodes the page path", () => {
    expect(feedbackUrl("/en/datasets/secop_co/ml", "en")).toContain("page=%2Fen%2Fdatasets%2Fsecop_co%2Fml");
  });
});

describe("Responsible-use notice", () => {
  it("links the guide in the UI language", () => {
    renderIn("es", <ResponsibleUse />);
    expect(screen.getByRole("heading", { name: "Usa estos resultados con responsabilidad" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lee la guía de uso responsable" })).toHaveAttribute(
      "href",
      expect.stringMatching(/docs\/responsible-use\.es\.md$/),
    );
  });
});

describe("Engine status on the landing", () => {
  it("stays quiet when the engine answers fast", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ status: "ok" })));
    renderIn("en", <EngineStatus />);
    expect(await screen.findByText("Engine ready")).toBeInTheDocument();
    expect(screen.queryByText("Starting the engine…")).not.toBeInTheDocument();
  });

  it("says the engine is starting while it wakes up, then that it is ready", async () => {
    vi.useFakeTimers();
    let wake: (r: Response) => void = () => {};
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(new Promise<Response>((resolve) => (wake = resolve)))
      .mockResolvedValue(json({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIn("es", <EngineStatus slowMs={2000} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Encendiendo el motor…");
    await act(async () => {
      wake(json({ status: "ok" }));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Motor listo");
  });

  it("never spins forever: offers a retry after the timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderIn("es", <EngineStatus slowMs={100} pollMs={1000} timeoutMs={5000} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("El motor no despertó");
    expect(screen.getByRole("button", { name: "Intentar de nuevo" })).toBeInTheDocument();
  });
});
