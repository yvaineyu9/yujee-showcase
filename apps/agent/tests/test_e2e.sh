#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$HERE/.." && pwd)"
cd "$AGENT_DIR"

if [[ ! -d .venv ]]; then
  echo "[setup] creating .venv"
  python3 -m venv .venv
  ./.venv/bin/pip install -q -e . >/dev/null
fi

SECRET="${AGENT_SHARED_SECRET:-dev_secret_e2e}"
AGENT_PORT="${AGENT_PORT:-8001}"
SINK_PORT="${SINK_PORT:-8002}"
SINK_LOG="$(mktemp -t agent_e2e_sink.XXXXXX.log)"
AGENT_LOG="$(mktemp -t agent_e2e_agent.XXXXXX.log)"
SAMPLE_PAYLOAD="$(mktemp -t agent_e2e_sample.XXXXXX.json)"
FAIL_PAYLOAD="$(mktemp -t agent_e2e_fail.XXXXXX.json)"

cleanup() {
  set +e
  [[ -n "${AGENT_PID:-}" ]] && kill "$AGENT_PID" 2>/dev/null
  [[ -n "${SINK_PID:-}" ]] && kill "$SINK_PID" 2>/dev/null
  wait 2>/dev/null
  rm -f "$SINK_LOG" "$AGENT_LOG" "$SAMPLE_PAYLOAD" "$FAIL_PAYLOAD"
}
trap cleanup EXIT

cat > "$SAMPLE_PAYLOAD" <<JSON
{
  "requestId": "req_e2e_ok",
  "prompt": "A spring day in Kyoto",
  "language": "en",
  "callbackUrl": "http://127.0.0.1:${SINK_PORT}/api/v1/internal/job-progress",
  "photos": [
    {"photoId": "p1", "base64": "data:image/jpeg;base64,AAA", "width": 800, "height": 600},
    {"photoId": "p2", "base64": "data:image/jpeg;base64,BBB", "width": 600, "height": 800},
    {"photoId": "p3", "base64": "data:image/jpeg;base64,CCC", "width": 800, "height": 800}
  ]
}
JSON

cat > "$FAIL_PAYLOAD" <<JSON
{
  "requestId": "req_e2e_fail",
  "prompt": "FAIL_TEST",
  "language": "en",
  "callbackUrl": "http://127.0.0.1:${SINK_PORT}/api/v1/internal/job-progress",
  "photos": [
    {"photoId": "p1", "base64": "data:image/jpeg;base64,AAA", "width": 800, "height": 600},
    {"photoId": "p2", "base64": "data:image/jpeg;base64,BBB", "width": 600, "height": 800},
    {"photoId": "p3", "base64": "data:image/jpeg;base64,CCC", "width": 800, "height": 800}
  ]
}
JSON

echo "[setup] starting callback sink on :${SINK_PORT}"
./.venv/bin/python -c "
import sys, json
from fastapi import FastAPI, Request
import uvicorn
app = FastAPI()
@app.post('/api/v1/internal/job-progress')
async def cb(req: Request):
    body = await req.json()
    print('CALLBACK ' + json.dumps(body)[:500], flush=True)
    return {'ok': True}
uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), log_level='warning')
" "$SINK_PORT" >"$SINK_LOG" 2>&1 &
SINK_PID=$!

echo "[setup] starting agent on :${AGENT_PORT}"
AGENT_SHARED_SECRET="$SECRET" PORT="$AGENT_PORT" \
  ./.venv/bin/uvicorn src.main:app --port "$AGENT_PORT" --log-level warning >"$AGENT_LOG" 2>&1 &
AGENT_PID=$!

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${AGENT_PORT}/health" >/dev/null; then break; fi
  sleep 0.25
done
for _ in $(seq 1 40); do
  if curl -sf -X OPTIONS "http://127.0.0.1:${SINK_PORT}/api/v1/internal/job-progress" >/dev/null 2>&1 \
    || curl -s -o /dev/null "http://127.0.0.1:${SINK_PORT}/api/v1/internal/job-progress"; then break; fi
  sleep 0.25
done

echo
echo "[test] GET /health"
curl -sf "http://127.0.0.1:${AGENT_PORT}/health"
echo

echo
echo "[test] POST /v1/layout (happy path)"
curl -sf -X POST "http://127.0.0.1:${AGENT_PORT}/v1/layout" \
  -H "Authorization: Bearer ${SECRET}" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req_e2e_ok" \
  -d @"$SAMPLE_PAYLOAD"
echo

echo
echo "[test] POST /v1/layout (FAIL_TEST)"
curl -sf -X POST "http://127.0.0.1:${AGENT_PORT}/v1/layout" \
  -H "Authorization: Bearer ${SECRET}" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req_e2e_fail" \
  -d @"$FAIL_PAYLOAD"
echo

echo "[wait] giving pipeline 12s to finish..."
sleep 12

echo
echo "[sink] callbacks received:"
echo
cat "$SINK_LOG"

OK_PROGRESS=$(grep -c '"event": "progress"' "$SINK_LOG" || true)
OK_COMPLETED=$(grep -c '"event": "completed"' "$SINK_LOG" || true)
OK_FAILED=$(grep -c '"event": "failed"' "$SINK_LOG" || true)

echo
echo "[summary] progress=$OK_PROGRESS completed=$OK_COMPLETED failed=$OK_FAILED"

if [[ "$OK_PROGRESS" -lt 9 ]]; then
  echo "FAIL: expected >= 9 progress callbacks (3 stages x 3 updates)"
  exit 1
fi
if [[ "$OK_COMPLETED" -lt 1 ]]; then
  echo "FAIL: expected >= 1 completed callback"
  exit 1
fi
if [[ "$OK_FAILED" -lt 1 ]]; then
  echo "FAIL: expected >= 1 failed callback"
  exit 1
fi

echo "PASS"
