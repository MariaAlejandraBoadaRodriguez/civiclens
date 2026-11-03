import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JurisdictionBars } from "@/components/dashboard/JurisdictionBars";
import { kpiTile } from "@/components/dashboard/kpiTiles";
import { MonthlyChart, monthLabel } from "@/components/dashboard/MonthlyChart";
import type { DashboardJurisdiction, DashboardKpi } from "@/lib/api-types";
import en from "@/messages/en.json";
import es from "@/messages/es.json";
import { renderIn } from "./render";

vi.mock("@/i18n/routing", () => ({ Link: (p: { children: unknown }) => p.children }));

const t = (messages: typeof en) => (key: string, values?: Record<string, string | number>) => {
  const template = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], messages.dashboard) as string;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(values?.[k] ?? ""));
};

const kpi = (over: Partial<DashboardKpi>): DashboardKpi => ({
  kpi_id: "total_spend",
  value: 412_600_000,
  unit: "currency",
  currency: "CAD",
  name: "Total spend",
  definition: "Sum of amount_cad",
  ...over,
});

describe("kpiTile", () => {
  it("formats spend with its change in each UI language", () => {
    expect(kpiTile(kpi({ change: 0.068 }), "en", t(en))).toMatchObject({ value: "CAD 412.6M", note: "+6.8% vs previous period", tone: "positive" });
    const tile = kpiTile(kpi({ change: -0.05 }), "es", t(es));
    expect(tile.value).toMatch(/^CAD 412,6\s?M$/);
    expect(tile.note).toMatch(/^-5\s?% vs\. periodo anterior$/);
  });

  it("shows direct-award change in points, flagged when it rises", () => {
    const tile = kpiTile(kpi({ kpi_id: "direct_award_share", unit: "ratio", value: 0.41, change_points: 0.03 }), "en", t(en));
    expect(tile).toMatchObject({ value: "41%", note: "+3 pts", tone: "attention" });
  });

  it("explains HHI with its level and quality with its score before cleaning", () => {
    expect(kpiTile(kpi({ kpi_id: "hhi", unit: "index", value: 0.031, level_label: "unconcentrated" }), "en", t(en)).note).toBe("unconcentrated");
    expect(kpiTile(kpi({ kpi_id: "quality_score", unit: "score", value: 81, before: 68 }), "es", t(es))).toMatchObject({ note: "antes 68", tone: "positive" });
    expect(kpiTile(kpi({ kpi_id: "quality_score", unit: "score", value: 88, before: 88 }), "en", t(en)).note).toBeUndefined();
  });

  it("never invents a value", () => {
    expect(kpiTile(kpi({ value: null }), "en", t(en)).value).toBe("—");
  });
});

describe("MonthlyChart", () => {
  const monthly = [
    { month: "2025-11", spend: 100, contracts: 3 },
    { month: "2025-12", spend: 400, contracts: 9 },
    { month: "2026-01", spend: 120, contracts: 4 },
  ];

  it("marks the peak month and labels the chart in Spanish", () => {
    const { container } = renderIn(
      "es",
      <MonthlyChart monthly={monthly} peak={{ ...monthly[1], ratio: 2.9, is_peak: true, flagged: 2 }} />,
    );
    expect(container.querySelectorAll("rect[data-peak]")).toHaveLength(1);
    expect(screen.getByRole("img")).toHaveAccessibleName(/Gráfico de barras del gasto mensual en CAD/);
    expect(screen.getByText("Ver las cifras")).toBeInTheDocument();
  });

  it("does not mark a peak when no month stands out", () => {
    const { container } = renderIn("en", <MonthlyChart monthly={monthly} peak={{ ...monthly[1], ratio: 1.4, is_peak: false, flagged: null }} />);
    expect(container.querySelectorAll("rect[data-peak]")).toHaveLength(0);
  });

  it("names months in the UI language", () => {
    expect(monthLabel("en", "2025-12", "long")).toMatch(/December 2025/);
    expect(monthLabel("es", "2025-12", "long")).toMatch(/diciembre/);
  });
});

describe("JurisdictionBars", () => {
  it("compares jurisdictions in one currency", () => {
    const item = (jurisdiction: "CO" | "CA", spend: number, share: number): DashboardJurisdiction => ({
      dataset_id: jurisdiction,
      slug: null,
      jurisdiction,
      name: jurisdiction,
      label: jurisdiction === "CO" ? "Colombia" : "Canadá (federal)",
      spend,
      contracts: 1200,
      share_of_max: share,
      origin: "clean",
      window: { start: null, end: null, fiscal_year: null },
    });
    renderIn("es", <JurisdictionBars items={[item("CA", 2_000_000, 1), item("CO", 500_000, 0.25)]} selected={["CO"]} />);
    const rows = screen.getAllByTestId("jurisdiction-row");
    expect(rows[0]).toHaveTextContent("Canadá (federal)");
    expect(rows[0]).toHaveTextContent("CAD");
    expect(rows[1]).toHaveTextContent("1.200 contratos");
    expect(rows[1]).toHaveAttribute("data-selected", "true");
    expect(rows[1]).toHaveTextContent("(seleccionada)");
    expect(rows[0]).not.toHaveAttribute("data-selected");
  });
});

describe("DashboardFilters", () => {
  it("keeps every filter when two change in quick succession", async () => {
    const replace = vi.fn();
    vi.doMock("@/i18n/routing", () => ({ usePathname: () => "/datasets/secop_co/dashboard", useRouter: () => ({ replace }) }));
    vi.resetModules();
    const { DashboardFilters } = await import("@/components/dashboard/DashboardFilters");
    const { fireEvent } = await import("@testing-library/react");
    renderIn(
      "en",
      <DashboardFilters scope="secop_co" scopes={[{ value: "secop_co", label: "Colombia" }, { value: "all", label: "All" }]} period="all" category="all" />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Jurisdiction" }), { target: { value: "all" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Period" }), { target: { value: "12m" } });
    expect(replace).toHaveBeenLastCalledWith("/datasets/secop_co/dashboard?scope=all&period=12m&category=all", { scroll: false });
    for (const key of ["scope", "period", "category"]) {
      const select = document.getElementById(`filter-${key}`) as HTMLSelectElement;
      expect(select.name).toBe(key); // id + name: autofill, labels and form tooling find them
    }
  });
});
