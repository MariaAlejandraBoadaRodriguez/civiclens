// Response shapes of the CivicLens API (see openapi.yaml). Machine fields are English and
// stable; `label`, `name`, `title`, `detail` arrive localized via Accept-Language.

export type Quality = {
  score: number;
  completeness: number;
  uniqueness: number;
  validity: number;
  consistency: number;
};

export type Dataset = {
  id: string;
  slug: string | null;
  name: string;
  description: string | null;
  source: "seed" | "upload" | "api";
  format: "csv" | "xlsx" | "json" | "parquet";
  data_lang: "en" | "fr" | "es" | "mixed" | "unknown";
  status: "uploaded" | "profiled" | "cleaned" | "modeled" | "failed" | "expired";
  rows: number | null;
  columns: number | null;
  quality_score: number | null;
  license: string | null;
  source_url: string | null;
  jurisdiction: string | null;
  created_at: string | null;
  expires_at: string | null;
};

export type InferredType = "string" | "integer" | "number" | "date" | "datetime" | "boolean" | "category";

export type ColumnProfile = {
  source_header: string;
  canonical_field: string | null;
  canonical_type: string | null;
  label: string | null;
  mapping_confidence: number;
  needs_check: boolean;
  candidates: string[];
  candidate_labels: Record<string, string>;
  inferred_type: InferredType;
  validity: number;
  consistency: number;
  notations: Record<string, number>;
  null_ratio: number;
  null_tokens: Record<string, number>;
  distinct: number;
  top_values: { value: string; count: number }[];
  data_lang: Record<string, number>;
  pii_kind: string | null;
  pii_label: string | null;
};

export type Profile = {
  dataset: Dataset;
  read: {
    format: string;
    encoding: string | null;
    encoding_label: string | null;
    delimiter: string | null;
    sheet: string | null;
    header_row: number;
    records_path: string | null;
  };
  size_bytes: number | null;
  rows: number;
  columns_count: number;
  duplicate_rows: number;
  duplicate_keys: number;
  invalid_rows: number;
  inconsistent_rows: number;
  data_lang: Record<string, number>;
  data_lang_label: Dataset["data_lang"];
  quality: Quality;
  pii: { field: string; kind: string; label: string }[];
  is_seed: boolean;
  columns: ColumnProfile[];
};

export type Problem = {
  type: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  params?: Record<string, unknown>;
};

export type Job = {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  dataset_id: string | null;
  result: Record<string, unknown> | null;
  error: Problem | null;
};

export type RecipeStep = { op: string; args: Record<string, unknown> };

export type KpiValue = {
  value: number | null;
  currency: string | null;
  unit?: "ratio";
  reason?: "mixed_currencies" | "not_standardized" | "no_amount";
  scope?: "dominant_currency";
};

export type IssueOption = {
  option_id: string;
  label: string;
  hint: string;
  recommended: boolean;
  steps: RecipeStep[];
  params: Record<string, unknown>;
};

export type PreviewCell = string | number | boolean | null;

export type Issue = {
  issue_id: string;
  issue_type: string;
  category: "completeness" | "uniqueness" | "validity" | "consistency";
  category_label: string;
  field: string | null;
  affected_rows: number;
  position: number;
  of: number;
  title: string;
  what: string;
  why: string;
  learn_more: string;
  fx_note?: string;
  options: IssueOption[];
  preview_columns: string[];
  preview_before: PreviewCell[][];
  preview_after: Record<string, PreviewCell[][]>;
  kpi_id: string | null;
  kpi_label: string | null;
  kpi_before: KpiValue | null;
  kpi_after: Record<string, KpiValue>;
};

export type IssuesResponse = {
  dataset: Dataset;
  quality: Quality | null;
  quality_after: Quality | null;
  columns: string[];
  issues: Issue[];
  op_labels: Record<string, string>;
};

export type ApplyResult = {
  output_hash: string;
  rows_before: number;
  rows_after: number;
  steps: { op: string; rows_before: number; rows_after: number; cells_changed: number }[];
  quality_before: Quality;
  quality_after: Quality;
};

export type Guardrails = { read_only: boolean; timeout_s: number; max_rows: number };

export type StarOrigin = "clean" | "recommended";

export type StarTable = {
  name: string;
  role: "fact" | "dimension";
  rows: number;
  columns: { name: string; type: string }[];
};

export type StarSchemaResponse = {
  dataset_id: string;
  origin: StarOrigin;
  tables: StarTable[];
  guardrails: Guardrails;
};

export type SqlConcept = "join" | "cte" | "window_function" | "aggregation" | "subquery";

export type GuidedQuery = {
  query_id: string;
  title: string;
  question: string;
  sql: string;
  explanation: string;
  concepts: SqlConcept[];
};

export type GuidedQueriesResponse = { items: GuidedQuery[]; guardrails: Guardrails };

export type QueryCell = string | number | boolean | null;

export type QueryResult = {
  columns: { name: string; type: string }[];
  rows: QueryCell[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
};

export type Kpi = {
  kpi_id: string;
  value: number | null;
  unit: "currency" | "count" | "ratio" | "index" | "score";
  currency: string | null;
  owner: string;
  formula_sql: string | null;
  name: string;
  definition: string;
};

export type KpisResponse = { dataset_id: string; origin: StarOrigin; items: Kpi[] };
