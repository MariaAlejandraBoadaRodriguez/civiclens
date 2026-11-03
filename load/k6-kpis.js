// Light load test (ROADMAP Phase 8): 20 virtual users on /kpis and /query, warm API.
// Target: p95 < 1.5 s, < 1 % failed requests. CI runs it against the API image in 512 MB:
//   k6 run -e BASE=http://127.0.0.1:8001 load/k6-kpis.js
import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE || "http://127.0.0.1:8000";
const SEEDS = ["secop_co", "contracts_ca", "contracts_qc"];
const SQL = [
  "SELECT s.supplier_name, SUM(f.amount_cad) AS spend FROM fact_contract f JOIN dim_supplier s USING (supplier_id) GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
  "SELECT d.fiscal_year, COUNT(*) AS contracts, SUM(f.amount_cad) AS spend FROM fact_contract f JOIN dim_date d USING (date_id) GROUP BY 1 ORDER BY 1",
  "SELECT award_type, COUNT(*) FROM fact_contract GROUP BY 1",
];

export const options = {
  scenarios: {
    light: { executor: "constant-vus", vus: 20, duration: "60s" },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500"],
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

// "Warm": every star schema is built and every query plan cached once before the clock starts.
export function setup() {
  for (const slug of SEEDS) {
    http.get(`${BASE}/api/v1/kpis/${slug}`, { timeout: "120s" });
    for (const sql of SQL) post(slug, sql, "120s");
  }
}

function post(slug, sql, timeout = "30s") {
  return http.post(`${BASE}/api/v1/query`, JSON.stringify({ dataset_id: slug, sql }), {
    headers: { "Content-Type": "application/json", "Accept-Language": __VU % 2 ? "es" : "en" },
    timeout,
    tags: { endpoint: "query" },
  });
}

export default function () {
  const slug = SEEDS[(__VU + __ITER) % SEEDS.length];
  const kpis = http.get(`${BASE}/api/v1/kpis/${slug}`, {
    headers: { "Accept-Language": __VU % 2 ? "es" : "en" },
    tags: { endpoint: "kpis" },
  });
  check(kpis, { "kpis 200": (r) => r.status === 200 });
  const query = post(slug, SQL[__ITER % SQL.length]);
  check(query, { "query 200": (r) => r.status === 200 && r.json("row_count") >= 1 });
}
