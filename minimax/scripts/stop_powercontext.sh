#!/usr/bin/env bash
# Stop the PowerContext server started by start_powercontext.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .runtime/powercontext.pid ]]; then
  PID="$(cat .runtime/powercontext.pid)"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for _ in $(seq 1 30); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 1
    done
    echo "stopped PowerContext pid $PID"
  else
    echo "PowerContext pid $PID is not running"
  fi
  rm -f .runtime/powercontext.pid
else
  echo "no .runtime/powercontext.pid; nothing to stop"
fi