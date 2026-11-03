#!/usr/bin/env bash
# Contract test (ROADMAP 5e DoD): Schemathesis fuzzes every operation in openapi.yaml against a
# fresh API and fails on 5xx, undocumented status codes or headers, schema violations, accepted
# invalid input, wrong Allow headers, missing auth handling and slow responses.
#
# Excluded on purpose (see the 5e PR, "Decisions taken"):
#   positive_data_acceptance — schema-valid but semantically invalid input (an empty CSV, a
#     recipe op with missing args, SQL that is not a SELECT, a PDF report) is refused with a
#     documented 400/406/422 problem. JSON Schema cannot express those business rules.
#   ignored_auth — authentication is optional by design on the public demo (ANONYMOUS_WRITES);
#     401/403 paths are covered by tests/test_public_api.py.
set -euo pipefail
cd "$(dirname "$0")/.."
WORK="${WORK:-$(mktemp -d)}"
PORT="${PORT:-8100}"
export DATABASE_URL="sqlite:///$WORK/civiclens.db" DATA_DIR="$WORK" JOB_RUNNER=fork \
  RATE_LIMIT_ANONYMOUS=1000000 RATE_LIMIT_HEAVY_ANONYMOUS=1000000
(cd apps/api && alembic upgrade head && python -m app.prebuild)  # warm star schemas, like the image
(cd apps/api && exec python -m uvicorn app.main:app --port "$PORT" >"$WORK/api.log" 2>&1) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
for _ in $(seq 60); do curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
st --no-color --config-file schemathesis.toml run openapi.yaml --url "http://127.0.0.1:$PORT" \
  --max-examples "${MAX_EXAMPLES:-10}" --seed "${SEED:-5}" --workers 1 \
  --request-timeout 120 --max-response-time 20
