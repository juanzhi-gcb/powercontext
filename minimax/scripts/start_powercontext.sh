#!/usr/bin/env bash
# Start the PowerContext server with an embedded seekdb backend.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi
PORT="${POWERCONTEXT_PORT:-8000}"
DATA_DIR="${POWERCONTEXT_DATA_DIR:-${PWD}/.powercontext}"
mkdir -p .runtime "$DATA_DIR"

if curl -sf "http://127.0.0.1:${PORT}/health/live" >/dev/null 2>&1; then
  echo "PowerContext already running on port ${PORT}"
  echo "$PORT" > .runtime/powercontext.port
  exit 0
fi

# Pick a free port when the requested one is taken by another process.
while (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; do
  PORT=$((PORT + 1))
  if [[ "$PORT" -gt 8100 ]]; then
    echo "no free port between 8000 and 8100" >&2
    exit 1
  fi
done
echo "$PORT" > .runtime/powercontext.port
echo "using port ${PORT}"

cat > .runtime/powercontext.env <<EOF
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=${PORT}
POWERCONTEXT_SERVER_DATABASE_KIND=seekdb
POWERCONTEXT_SERVER_DATABASE_PATH=${DATA_DIR}/seekdb
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_MCP_ENABLED=true
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
POWERCONTEXT_SERVER_LOGGING_LEVEL=INFO
POWERCONTEXT_SERVER_LOGGING_FORMAT=console
EOF

nohup .venv/bin/powercontext server run --env-file .runtime/powercontext.env \
  > .runtime/powercontext.log 2>&1 &
echo $! > .runtime/powercontext.pid

for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${PORT}/health/ready" >/dev/null 2>&1; then
    echo "PowerContext ready on http://127.0.0.1:${PORT} (pid $(cat .runtime/powercontext.pid))"
    exit 0
  fi
  sleep 1
done

echo "PowerContext failed to become ready; last log lines:" >&2
tail -30 .runtime/powercontext.log >&2
exit 1
