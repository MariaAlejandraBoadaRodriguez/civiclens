import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DomainStep } from "@/components/ingest/DomainStep";
import { SqlLab } from "@/components/sql/SqlLab";
import type { DomainResponse } from "@/lib/api-types";
import { json, renderIn } from "./render";

const packs: DomainResponse["packs"] = [
  { id: "government", name: "Government", description: "Contracts", goals: [{ id: "spend_overview", name: "Spend", default: true }], roles: [] },
  {
    id: "banking",
    name: "Banking",
    description: "Loans",
    goals: [
      { id: "credit_risk", name: "Credit risk", default: true },
      { id: "portfolio", name: "Portfolio", default: false },
    ],
    roles: [
      { id: "default_flag", name: "Default flag", kinds: ["boolean", "binary"], key: true, target: true, sensitive: false },
      { id: "age", name: "Age", kinds: ["integer"], key: false, target: false, sensitive: true },
    ],
  },
  { id: "general", name: "General", description: "Any table", goals: [{ id: "explore", name: "Explore", default: true }], roles: [] },
];

const domain: DomainResponse = {
  dataset_id: "d1",
  pack: "banking",
  goal: "credit_risk",
  confirmed: false,
  roles: { default_flag: { column: "credit_risk", source: "credit_risk", confidence: 0.95, positive: "False" } },
  suggestions: [
    { pack: "banking", score: 0.69, name: "Banking" },
    { pack: "general", score: 0.3, name: "General" },
    { pack: "government", score: 0, name: "Government" },
  ],
  packs,
  columns: [
    { name: "credit_risk", source: "credit_risk", kind: "boolean", kind_label: "Yes / no", binary: true, examples: ["True"], top: ["True", "False"] },
    { name: "age", source: "age", kind: "integer", kind_label: "Whole number", binary: false, examples: ["35"], top: [] },
    { name: "purpose", source: "purpose", kind: "category", kind_label: "Category", binary: false, examples: ["car"], top: [] },
  ],
  job: null,
};

describe("Domain step", () => {
  it("shows the suggestion, the confidence and only the columns a role accepts", () => {
    renderIn("en", <DomainStep domain={domain} datasetRef="d1" sample={false} />);
    expect(screen.getByText("Suggested: Banking")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Banking/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Government/ })).toBeDisabled(); // no procurement columns
    expect(screen.getByText(/^95\s?%$/)).toBeInTheDocument();
    const age = screen.getByRole("combobox", { name: /Age/ });
    expect([...age.querySelectorAll("option")].map((o) => o.textContent)).toEqual(["Not mapped", "age · Whole number"]);
    expect(screen.getByText("Sensitive")).toBeInTheDocument();
  });

  it("saves the pack, goal and edited roles with PUT, in Spanish", async () => {
    const saved = { ...domain, confirmed: true, goal: "portfolio", roles: { ...domain.roles, age: { column: "age", confidence: 1 } } };
    const fetchMock = vi.fn().mockResolvedValue(json(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderIn("es", <DomainStep domain={domain} datasetRef="d1" sample={false} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Objetivo del análisis" }), { target: { value: "portfolio" } });
    fireEvent.change(screen.getByRole("combobox", { name: /Age/ }), { target: { value: "age" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar este dominio" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Dominio guardado: Banking");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/datasets/d1/domain");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      pack: "banking",
      goal: "portfolio",
      roles: { default_flag: { column: "credit_risk", positive: "False" }, age: { column: "age", positive: null } },
    });
  });

  it("a sample dataset is read-only and says why", () => {
    renderIn("en", <DomainStep domain={domain} datasetRef="secop_co" sample />);
    expect(screen.queryByRole("button", { name: /Confirm|Save/ })).not.toBeInTheDocument();
    expect(screen.getByText(/sample datasets keep their domain/)).toBeInTheDocument();
  });
});

describe("SQL lab concepts", () => {
  it("translates known concepts and shows generated ones as SQL keywords", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    const guided = [
      { query_id: "counts_job", title: "Rows per job", question: "How are the rows distributed across job?", sql: "SELECT 1", explanation: "x", concepts: ["GROUP BY", "cte"] },
    ];
    renderIn("es", <SqlLab datasetRef="d1" guided={guided} guardrails={{ read_only: true, timeout_s: 10, max_rows: 10000 }} />);
    expect(screen.getByText("GROUP BY")).toBeInTheDocument();
    expect(screen.getByText("CTE")).toBeInTheDocument();
  });
});
