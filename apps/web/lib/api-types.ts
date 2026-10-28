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
