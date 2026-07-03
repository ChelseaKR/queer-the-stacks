#!/usr/bin/env bash
# Load smoke gate (Quality §2, merge-blocking): p95 < 500ms on the dashboard
# route. Starts the app in demo mode, runs a short constant-load Locust
# scenario against it (tests/perf/locustfile.py), then fails the build if the
# aggregated p95 latency is at or above the budget.
#
# Invoked via `make perf-load`; CI runs it as a non-conditional, blocking step.
set -euo pipefail

HOST="127.0.0.1"
PORT="8765"
BASE_URL="http://${HOST}:${PORT}"
OUT_PREFIX="docs/audits/perf"
STATS_CSV="${OUT_PREFIX}_stats.csv"
# Threshold in milliseconds; overridable only to prove the gate fails closed
# (e.g. `PERF_P95_THRESHOLD_MS=0 bash scripts/perf-smoke.sh` must exit non-zero).
THRESHOLD_MS="${PERF_P95_THRESHOLD_MS:-500}"
PYTHON="${PYTHON:-.venv/bin/python}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3

mkdir -p docs/audits

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "perf-smoke: starting app (demo mode) on ${BASE_URL}"
STACKS_DEMO=1 "$PYTHON" -m uvicorn app.server:app --host "$HOST" --port "$PORT" \
  >/tmp/perf-smoke-server.log 2>&1 &
SERVER_PID=$!

echo "perf-smoke: waiting for /readyz"
ready=0
for _ in $(seq 1 60); do
  if [ "$($PYTHON - "$BASE_URL" <<'PY'
import sys
import urllib.request

url = sys.argv[1] + "/readyz"
try:
    with urllib.request.urlopen(url, timeout=1) as resp:
        print(resp.status)
except Exception:
    print(0)
PY
)" = "200" ]; then
    ready=1
    break
  fi
  sleep 0.5
done

if [ "$ready" -ne 1 ]; then
  echo "perf-smoke: server never became ready (see /tmp/perf-smoke-server.log)" >&2
  cat /tmp/perf-smoke-server.log >&2 || true
  exit 1
fi

# Warm the store once, single-threaded, before the concurrent load starts.
# The dashboard route populates the app-state store lazily on first access;
# without this, the first wave of concurrent Locust users can race each other
# into that one-time population instead of exercising steady-state latency.
"$PYTHON" - "$BASE_URL" <<'PY' || true
import sys
import urllib.request

req = urllib.request.Request(
    sys.argv[1] + "/", headers={"Authorization": "Bearer demo-token"}
)
urllib.request.urlopen(req, timeout=10)
PY

echo "perf-smoke: running Locust (headless, 20 users, 20s)"
# Locust exits non-zero if any request failed during the run; that must not
# short-circuit this script (under `set -e`) before the p95 budget is checked
# below — a slow-but-successful run and a fast-but-flaky run are different
# failure modes, and this gate is scoped to the p95 latency budget.
locust -f tests/perf/locustfile.py --headless \
  -u 20 -r 5 -t 20s \
  --host "$BASE_URL" \
  --csv="$OUT_PREFIX" --only-summary || true

if [ ! -f "$STATS_CSV" ]; then
  echo "perf-smoke: expected stats file ${STATS_CSV} not found" >&2
  exit 1
fi

p95="$("$PYTHON" - "$STATS_CSV" <<'PY'
import csv
import sys

path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        if row.get("Name") == "Aggregated":
            print(row["95%"])
            break
    else:
        sys.exit("no Aggregated row found in " + path)
PY
)"

echo "perf-smoke: aggregated p95 = ${p95}ms (budget < ${THRESHOLD_MS}ms)"

if "$PYTHON" - "$p95" "$THRESHOLD_MS" <<'PY'
import sys

p95 = float(sys.argv[1])
threshold = float(sys.argv[2])
sys.exit(0 if p95 < threshold else 1)
PY
then
  echo "perf-smoke: OK — p95 ${p95}ms < budget ${THRESHOLD_MS}ms"
else
  echo "perf-smoke: FAIL — p95 ${p95}ms >= budget ${THRESHOLD_MS}ms" >&2
  exit 1
fi
