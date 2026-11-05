// Capacity for the public pre-launch: 10 concurrent visitors doing the main flow.
//
// Each iteration is one visitor session with think time between pages:
//   browse a sample  → profile, issues, a cleaning preview, the SQL lab (schema, questions,
//                      two queries, KPIs), the ML lab (latest red flags + forecast), the
//                      dashboard and the HTML report;
//   every 3rd session → "check your own data": upload a small CSV, wait for the job, read the
//                      domain and the dashboard overview, train the prediction model.
// Uploads and model runs are "heavy" calls: the API allows 12 per minute per caller.
//
//   k6 run -e BASE=http://127.0.0.1:8000 load/k6-visitors.js                  # one shared IP
//   k6 run -e BASE=... -e UNIQUE_IPS=1 load/k6-visitors.js  # 10 IPs (API with TRUSTED_PROXY_HOPS=1)
// Options: VUS (10), DURATION (3m), FILE (CSV to upload, default the German credit fixture).
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.BASE || "http://127.0.0.1:8000";
const VUS = Number(__ENV.VUS || 10);
const UNIQUE_IPS = __ENV.UNIQUE_IPS === "1";
const SEEDS = ["secop_co", "contracts_ca", "contracts_qc"];
const CSV = open(__ENV.FILE || "../data/fixtures/german_credit.csv", "b");

const rateLimited = new Counter("rate_limited_429");
const serverErrors = new Counter("server_errors_5xx");
const pageTime = new Trend("page_ms", true);
const ownDataTime = new Trend("own_data_flow_ms", true);

export const options = {
  scenarios: {
    visitors: { executor: "constant-vus", vus: VUS, duration: __ENV.DURATION || "3m" },
  },
  // MODE=measure (CI at 0.1 CPU): only correctness fails the run; latencies are reported.
  thresholds: __ENV.MODE === "measure" ? {
    server_errors_5xx: ["count==0"],
    "http_req_duration{kind:page}": ["p(95)<600000"],
    "http_req_duration{kind:heavy}": ["p(95)<600000"],
    "http_req_duration{endpoint:report}": ["p(95)<600000"],
  } : {
    server_errors_5xx: ["count==0"],
    "http_req_duration{kind:page}": ["p(95)<3000"],
    "http_req_duration{kind:heavy}": ["p(95)<60000"], // reported; a 202 comes back at once
    "http_req_duration{endpoint:report}": ["p(95)<10000"],
    checks: ["rate>0.95"],
  },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "max"],
};

function headers(extra = {}) {
  const h = { "Accept-Language": __VU % 2 ? "es" : "en", ...extra };
  if (UNIQUE_IPS) h["X-Forwarded-For"] = `10.20.0.${__VU}`;
  return h;
}

function record(res, name) {
  if (res.status === 429) rateLimited.add(1, { endpoint: name });
  if (res.status >= 500) serverErrors.add(1, { endpoint: name });
  return res;
}

function get(path, name, kind = "page", timeout = "60s") {
  const res = http.get(`${BASE}${path}`, { headers: headers(), tags: { endpoint: name, kind }, timeout });
  return record(res, name);
}

function post(path, body, name, kind = "page", timeout = "60s") {
  const res = http.post(`${BASE}${path}`, JSON.stringify(body), {
    headers: headers({ "Content-Type": "application/json" }),
    tags: { endpoint: name, kind },
    timeout,
  });
  return record(res, name);
}

function think() {
  sleep(1 + Math.random() * 2);
}

// Warm: build every model once and run the sample models, as production does after a deploy.
export function setup() {
  for (const slug of SEEDS) {
    http.get(`${BASE}/api/v1/datasets/${slug}/schema`, { timeout: "180s" });
    for (const model of ["red_flags", "forecast"]) {
      http.post(`${BASE}/api/v1/models/${model}/run`, JSON.stringify({ dataset_id: slug }), {
        headers: { "Content-Type": "application/json", "X-Forwarded-For": "10.99.0.1" },
      });
    }
  }
  sleep(20); // let the model jobs finish
}

function browse(slug) {
  const t0 = Date.now();
  check(get("/health", "health"), { health: (r) => r.status === 200 });
  get("/api/v1/datasets", "datasets");
  check(get(`/api/v1/datasets/${slug}/profile`, "profile"), { profile: (r) => r.status === 200 });
  think();
  const issues = get(`/api/v1/datasets/${slug}/issues`, "issues");
  if (issues.status === 200) {
    const data = issues.json();
    const first = data.issues[0];
    if (first) {
      post("/api/v1/recipes/preview", { steps: first.options[0].steps, columns: data.columns, name: slug }, "preview");
    }
  }
  think();
  get(`/api/v1/datasets/${slug}/schema`, "schema");
  const guided = get(`/api/v1/guided-queries?dataset_id=${slug}`, "guided");
  if (guided.status === 200) {
    for (const q of guided.json().items.slice(0, 2)) {
      check(post("/api/v1/query", { dataset_id: slug, sql: q.sql }, "query"), { query: (r) => r.status === 200 });
    }
  }
  get(`/api/v1/kpis/${slug}`, "kpis");
  think();
  get(`/api/v1/models/red_flags/latest?dataset_id=${slug}`, "ml_latest");
  get(`/api/v1/models/forecast/latest?dataset_id=${slug}`, "ml_latest");
  think();
  check(get(`/api/v1/dashboard?dataset_id=${slug}`, "dashboard"), { dashboard: (r) => r.status === 200 });
  get(`/api/v1/reports/${slug}?lang=es`, "report", "page", "90s");
  pageTime.add(Date.now() - t0);
}

function ownData() {
  const t0 = Date.now();
  const res = record(
    http.post(`${BASE}/api/v1/datasets`, { file: http.file(CSV, `visitor-${__VU}.csv`, "text/csv") }, {
      headers: headers(),
      tags: { endpoint: "upload", kind: "heavy" },
      timeout: "120s",
    }),
    "upload",
  );
  if (!check(res, { "upload accepted": (r) => r.status === 202 })) return;
  const { dataset, job } = res.json();
  let status = "queued";
  for (let i = 0; i < 90 && !["succeeded", "failed"].includes(status); i++) {
    sleep(1);
    const j = get(`/api/v1/jobs/${job.id}`, "job", "poll");
    if (j.status === 200) status = j.json().status;
  }
  if (!check(status, { "ingest succeeded": (s) => s === "succeeded" })) return;
  get(`/api/v1/datasets/${dataset.id}/domain`, "domain");
  check(get(`/api/v1/datasets/${dataset.id}/overview`, "overview", "page", "120s"), {
    overview: (r) => r.status === 200,
  });
  const run = post("/api/v1/models/target_model/run", { dataset_id: dataset.id }, "model_run", "heavy");
  check(run, { "model accepted": (r) => r.status === 202 });
  ownDataTime.add(Date.now() - t0);
}

export default function () {
  browse(SEEDS[(__VU + __ITER) % SEEDS.length]);
  if (__ITER % 3 === __VU % 3) ownData();
  think();
}

export function handleSummary(data) {
  const m = data.metrics;
  const v = (name, stat) => (m[name] && m[name].values[stat] !== undefined ? m[name].values[stat] : 0);
  const lines = [
    `CivicLens capacity · ${VUS} visitors · ${UNIQUE_IPS ? "one IP each" : "one shared IP"} · ${BASE}`,
    `sessions (iterations):       ${v("iterations", "count")}`,
    `requests:                    ${v("http_reqs", "count")}  (${v("http_reqs", "rate").toFixed(1)}/s)`,
    `page requests p50 / p95:     ${v("http_req_duration{kind:page}", "p(50)").toFixed(0)} / ${v("http_req_duration{kind:page}", "p(95)").toFixed(0)} ms`,
    `heavy requests p95:          ${v("http_req_duration{kind:heavy}", "p(95)").toFixed(0)} ms`,
    `HTML report p95:             ${v("http_req_duration{endpoint:report}", "p(95)").toFixed(0)} ms`,
    `browse session p50 / p95:    ${(v("page_ms", "p(50)") / 1000).toFixed(1)} / ${(v("page_ms", "p(95)") / 1000).toFixed(1)} s (incl. think time)`,
    `own-data flow p50 / p95:     ${(v("own_data_flow_ms", "p(50)") / 1000).toFixed(1)} / ${(v("own_data_flow_ms", "p(95)") / 1000).toFixed(1)} s`,
    `429 rate-limited:            ${v("rate_limited_429", "count")}`,
    `5xx server errors:           ${v("server_errors_5xx", "count")}`,
    `checks passed:               ${(v("checks", "rate") * 100).toFixed(1)} %`,
  ];
  return { stdout: lines.join("\n") + "\n", "k6-visitors-summary.json": JSON.stringify(data, null, 2) };
}
