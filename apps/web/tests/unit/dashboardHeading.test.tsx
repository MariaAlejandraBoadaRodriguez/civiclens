import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardHeading, headingFor } from "@/components/dashboard/DashboardHeading";
import en from "@/messages/en.json";
import es from "@/messages/es.json";
import { renderIn } from "./render";

const h1 = () => screen.getByRole("heading", { level: 1 });

describe("Dashboard heading follows the domain pack", () => {
  it("picks procurement only for procurement data, else the pack, else the dataset name", () => {
    expect(headingFor({ procurement: true, pack: null, name: "x" })).toEqual({ kind: "procurement" });
    expect(headingFor({ procurement: false, pack: "government", name: "x" })).toEqual({ kind: "procurement" });
    expect(headingFor({ procurement: false, pack: "marketing", name: "bank_marketing" })).toEqual({
      kind: "pack",
      pack: "marketing",
      name: "bank_marketing",
    });
    expect(headingFor({ procurement: false, pack: "general", name: "sales.xlsx" })).toEqual({ kind: "generic", name: "sales.xlsx" });
    expect(headingFor({ procurement: false, pack: null, name: "sales.xlsx" })).toEqual({ kind: "generic", name: "sales.xlsx" });
    expect(headingFor({ procurement: false })).toEqual({ kind: "unknown" });
  });

  it("a Marketing dataset (bank_marketing) never shows the procurement title or CAD note, in EN and ES", () => {
    for (const [locale, m] of [["en", en], ["es", es]] as const) {
      const { unmount } = renderIn(
        locale,
        <DashboardHeading spec={headingFor({ procurement: false, pack: "marketing", name: "bank_marketing.csv" })} />,
      );
      expect(h1()).toHaveTextContent(m.dashboard.heading.marketing.title);
      expect(h1()).not.toHaveTextContent(m.dashboard.title);
      const sub = screen.getByTestId("dashboard-heading");
      expect(sub).toHaveTextContent("bank_marketing.csv");
      expect(sub).not.toHaveTextContent("CAD");
      unmount();
    }
    renderIn("es", <DashboardHeading spec={{ kind: "pack", pack: "marketing", name: "b.csv" }} />);
    expect(h1()).toHaveTextContent("Marketing · vista de campañas");
  });

  it("falls back to the dataset name for the General pack", () => {
    renderIn("es", <DashboardHeading spec={headingFor({ procurement: false, pack: "general", name: "ventas.xlsx" })} />);
    expect(h1()).toHaveTextContent("ventas.xlsx · vista general");
    expect(h1()).not.toHaveTextContent("Contratación pública");
  });

  it("keeps the procurement heading for procurement data", () => {
    renderIn("es", <DashboardHeading spec={headingFor({ procurement: true })} />);
    expect(h1()).toHaveTextContent("Contratación pública · vista ejecutiva");
  });
});
