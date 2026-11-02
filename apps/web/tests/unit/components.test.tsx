import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CleaningStudio } from "@/components/cleaning/CleaningStudio";
import { Dropzone } from "@/components/ingest/Dropzone";
import { MlLab } from "@/components/ml/MlLab";
import { SqlLab } from "@/components/sql/SqlLab";
import type { IssuesResponse } from "@/lib/api-types";
import { badGateway, json, renderIn } from "./render";

const guided = [
  { query_id: "top_suppliers", title: "Top", question: "Who are the top suppliers?", sql: "SELECT 1 AS n", explanation: "x", concepts: [] },
];
const guardrails = { read_only: true, timeout_s: 10, max_rows: 10000 };
const queryResult = { columns: [{ name: "n", type: "INTEGER" }], rows: [[1]], row_count: 1, truncated: false, elapsed_ms: 3 };

describe("SQL lab", () => {
  it.each([
    ["en", "The engine did not answer", "Retry", "Results"],
    ["es", "El motor no respondió", "Reintentar", "Resultados"],
  ] as const)("a 502 on the query shows a %s message with Retry, and Retry recovers", async (locale, title, retry, results) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(badGateway()).mockResolvedValue(json(queryResult));
    vi.stubGlobal("fetch", fetchMock);
    renderIn(locale, <SqlLab datasetRef="secop_co" guided={guided} guardrails={guardrails} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(title);
    fireEvent.click(screen.getByRole("button", { name: retry }));
    expect(await screen.findByRole("heading", { level: 3, name: new RegExp(`^${results}`) })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("ML lab", () => {
  it("a network error while training shows the message with Retry, never a silent spinner", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderIn("es", <MlLab datasetRef="secop_co" redFlags={null} forecast={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("El motor no respondió");
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("Upload", () => {
  it("a 502 on upload shows the message and Retry sends the file again", async () => {
    const fetchMock = vi.fn().mockResolvedValue(badGateway());
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderIn("en", <Dropzone />);
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" })] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("The engine did not answer");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});

const issuesResponse = {
  dataset: { id: "d1", slug: "secop_co", name: "SECOP", source: "seed", format: "csv", data_lang: "es", status: "profiled" },
  quality: { score: 70 },
  quality_after: null,
  columns: ["supplier_name"],
  op_labels: { unify_variants: "Unify variants" },
  issues: [
    {
      issue_id: "text_variants:supplier_name",
      issue_type: "text_variants",
      category: "consistency",
      category_label: "Consistency",
      field: "supplier_name",
      affected_rows: 3,
      position: 1,
      of: 1,
      title: "Supplier names are written in several ways",
      what: "x",
      why: "y",
      learn_more: "z",
      options: [
        { option_id: "unify", label: "Unify", hint: "", recommended: true, params: {}, steps: [{ op: "unify_variants", args: { column: "supplier_name" } }] },
      ],
      preview_columns: ["supplier_name"],
      preview_before: [["ACME"]],
      preview_after: { unify: [["Acme"]] },
      kpi_id: null,
      kpi_label: null,
      kpi_before: null,
      kpi_after: {},
    },
  ],
} as unknown as IssuesResponse;

describe("Cleaning studio", () => {
  it("a failed recipe preview (the production 502) is shown with Retry instead of being swallowed", async () => {
    const code = { pandas: "df = clean(df)", sql: "SELECT 1", json: "{}" };
    const fetchMock = vi.fn().mockResolvedValueOnce(badGateway()).mockResolvedValue(json(code));
    vi.stubGlobal("fetch", fetchMock);
    renderIn("en", <CleaningStudio data={issuesResponse} datasetRef="secop_co" />);
    expect(await screen.findByRole("alert", {}, { timeout: 3000 })).toHaveTextContent("The engine did not answer");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull(), { timeout: 3000 });
    expect(fetchMock.mock.calls.every(([url]) => String(url).endsWith("/api/v1/recipes/preview"))).toBe(true);
  });
});
