#!/usr/bin/env bash
# End-to-end verification sample.
#
#   ./scripts/run_sample.sh --replay   # uses the recorded MiniMax response (no API key)
#   ./scripts/run_sample.sh --live     # calls MiniMax with MINIMAX_API_KEY
#
# The script always starts from an empty seekdb database and an empty
# PowerContext state directory so every run is reproducible.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:---replay}"
TASK_FILE="tasks/TASK-ORD-003.md"
export PYTHONPATH="$PWD"

if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi
PY=".venv/bin/python"
[[ -x "$PY" ]] || { echo "run scripts/bootstrap.sh first" >&2; exit 1; }

echo "== 1/8 reset workspace and start PowerContext from empty state =="
bash scripts/stop_powercontext.sh >/dev/null 2>&1 || true
rm -rf .powercontext .seekdb .sdd_state
bash scripts/start_powercontext.sh
export POWERCONTEXT_URL="http://127.0.0.1:$(cat .runtime/powercontext.port)"

echo "== 2/8 initialise and import engineering material into seekdb =="
$PY -m sdd_context.cli init --drop
$PY -m sdd_context.cli ingest

echo "== 3/8 restore the business project to the pre-change snapshot =="
if [[ -d evidence/code/before ]]; then
  $PY -m sdd_context.cli reset-demo
fi

echo "== 4/8 build the task context =="
$PY -m sdd_context.cli context --task-file "$TASK_FILE" --out .runtime/context.json >/dev/null
TASK_ID="$($PY -c 'import json;print(json.load(open(".runtime/context.json"))["task_id"])')"
echo "task id: $TASK_ID"

echo "== 5/8 baseline: target tests must fail before the change =="
$PY -m sdd_context.cli baseline --task-id "$TASK_ID" --expect fail

echo "== 6/8 apply the MiniMax change =="
if [[ "$MODE" == "--live" ]]; then
  $PY -m sdd_context.cli patch --task-id "$TASK_ID" > .runtime/patch.json
else
  REPLAY_FILE="${REPLAY_FILE:-evidence/minimax/recorded-response.json}"
  $PY -m sdd_context.cli patch --task-id "$TASK_ID" --replay "$REPLAY_FILE" > .runtime/patch.json
fi

echo "== 7/8 verification: target and regression suites =="
$PY -m sdd_context.cli verify --task-id "$TASK_ID"
$PY -m sdd_context.cli snapshot --label after >/dev/null

echo "== 8/8 restart the module and reuse the saved state =="
mkdir -p evidence/powercontext
$PY -m sdd_context.cli status --task-id "$TASK_ID" | tee evidence/powercontext/status-before-restart.txt
bash scripts/stop_powercontext.sh
bash scripts/start_powercontext.sh
$PY -m sdd_context.cli status --task-id "$TASK_ID" | tee evidence/powercontext/status-after-restart.txt

echo "sample finished; patch, logs and state evidence are under evidence/"
echo "run ./scripts/reset_demo.sh to restore the business project"