import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GenericMlLab } from "@/components/ml/GenericMlLab";
import type { DataColumn, TargetModelResult } from "@/lib/api-types";
import { json, renderIn } from "./render";

const columns: DataColumn[] = [
  { name: "y", source: "y", kind: "boolean", kind_label: "Sí / no", sql_type: "BOOLEAN", binary: true, nulls: 0, distinct: 2, examples: [] },
  { name: "age", source: "age", kind: "integer", kind_label: "Número entero", sql_type: "BIGINT", binary: false, nulls: 0, distinct: 70, examples: [] },
  { name: "id", source: "id", kind: "identifier", kind_label: "Identificador", sql_type: "VARCHAR", binary: false, nulls: 0, distinct: 500, examples: [] },
];

const card = {
  name: "Modelo de predicción",
  question: "¿Qué filas probablemente tendrán y = sí?",
  method: "Gradient boosting",
  warning: "Un modelo encuentra patrones, no causas.",
  limitations: ["l1"],
  features: [{ id: "duration", label: "duration" }],
  notes: ["Posible fuga de información: duration"],
  verdict: "El modelo supera a la línea base: AUC ROC 0,93 vs 0,5.",
  metric_labels: { roc_auc: "AUC ROC" },
};

const result: TargetModelResult = {
  model_type: "target_model",
  status: "ok",
  task: "binary",
  target: "y",
  positive: "True",
  metrics: { roc_auc: 0.93 },
  baseline_metrics: { roc_auc: 0.5 },
  beats_baseline: true,
  importance: [{ feature: "duration", label: "duration", importance: 0.2, share: 0.78 }],
  leakage: [{ feature: "duration", strength: 0.82, reason: "name_and_strength" }],
  fairness: [
    {
      attribute: "age",
      column: "age",
      label: "Edad",
      verdict: "Alerta de equidad según age",
      disparity_ratio: 0.3,
      passes: false,
      groups: [{ group: "<25", rows: 36, actual_rate: 0.3, flagged_rate: 0.28, true_positive_rate: 0.5, false_positive_rate: 0.1 }],
    },
  ],
  card,
};

const initial = { target: result, anomalies: null, segments: null, forecast: null };

describe("Generic ML lab", () => {
  it("shows the verdict, the leakage warning and the fairness check in Spanish", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderIn("es", <GenericMlLab datasetRef="d1" columns={columns} initial={initial} />);
    expect(screen.getByTestId("model-verdict")).toHaveTextContent("supera a la línea base");
    expect(screen.getByText("Revisa estas columnas antes de confiar en el puntaje")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Revisión de equidad · Edad" })).toBeInTheDocument();
    // Only predictable columns are offered (not the identifier).
    const select = screen.getByRole("combobox", { name: "Columna a predecir" });
    expect([...select.querySelectorAll("option")].map((o) => o.value)).toEqual(["", "y", "age"]);
  });

  it("trains on the column the user picks", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ id: "j1", status: "queued" }, 202))
      .mockResolvedValueOnce(json({ id: "j1", status: "succeeded" }))
      .mockResolvedValue(json({ ...result, target: "age", task: "regression" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIn("en", <GenericMlLab datasetRef="d1" columns={columns} initial={initial} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Column to predict" }), { target: { value: "age" } });
    fireEvent.click(screen.getByRole("button", { name: "Train the model" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/models/target_model/run");
    expect(JSON.parse(init.body)).toEqual({ dataset_id: "d1", params: { target: "age" } });
  });
});
