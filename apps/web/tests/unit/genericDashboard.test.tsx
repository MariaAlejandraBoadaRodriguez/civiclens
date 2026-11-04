import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GenericDashboard } from "@/components/dashboard/GenericDashboard";
import type { Overview } from "@/lib/api-types";
import { json, renderIn } from "./render";

const overview: Overview = {
  dataset_id: "d1",
  origin: "recommended",
  domain: { pack: "banking", goal: "credit_risk", name: "Banca / crédito" },
  rows: 1000,
  columns: 21,
  quality: { before: 92, after: null },
  kpis: [
    { kpi_id: "banking.default_rate", value: 0.3, unit: "ratio", currency: null, owner: "banking", formula_sql: null, name: "Tasa de incumplimiento", definition: "d" },
  ],
  sections: [
    {
      id: "drivers",
      chart: "bar",
      unit: "ratio",
      title: "Tasa de credit_risk por purpose",
      finding: "purpose = retraining tiene la mayor tasa de credit_risk: 44,0 % frente a 30,0 % en total.",
      x_label: "",
      y_label: "",
      rows: [{ label: "retraining", value: 0.44 }],
      sql: "SELECT 1",
    },
  ],
  dimensions: [{ name: "purpose", source: "purpose", kind: "category" }],
  metrics: [{ name: "amount", source: "amount" }],
};

describe("Generic dashboard", () => {
  it("shows KPI tiles, the quality line and each finding in Spanish", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderIn("es", <GenericDashboard overview={overview} datasetRef="d1" />);
    expect(screen.getByText("Tasa de incumplimiento")).toBeInTheDocument();
    expect(screen.getByTestId("quality")).toHaveTextContent("Puntaje de calidad 92");
    expect(screen.getByTestId("finding")).toHaveTextContent("44,0 %");
    expect(screen.getByText(/^44(,0)?\s?%$/)).toBeInTheDocument();
  });

  it("the chart builder sends the chosen spec and draws the result as a table", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      json({ sql: "SELECT", chart: "table", rows: [{ label: "car", value: 3200 }], dimension: "purpose", aggregation: "avg", metric: "amount" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIn("en", <GenericDashboard overview={overview} datasetRef="d1" />);
    fireEvent.change(screen.getByRole("combobox", { name: "Chart" }), { target: { value: "table" } });
    fireEvent.click(screen.getByRole("button", { name: "Draw the chart" }));
    await waitFor(() => expect(screen.getByRole("cell", { name: "car" })).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/datasets/d1/chart");
    expect(JSON.parse(init.body)).toEqual({ dimension: "purpose", aggregation: "avg", metric: "amount", chart_type: "table", filters: [] });
  });
});
