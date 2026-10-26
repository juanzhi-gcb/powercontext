#!/usr/bin/env bash
# Create the virtualenv and install the pinned runtime.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
INDEX_ARGS=()
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  INDEX_ARGS=(--index-url "$PIP_INDEX_URL")
fi

if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .venv
  else
    "$PYTHON_BIN" -m venv .venv
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python "${INDEX_ARGS[@]}" -r requirements.txt
else
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install "${INDEX_ARGS[@]}" -r requirements.txt
fi

echo "virtualenv ready: $PWD/.venv"
echo "python: $(.venv/bin/python -V)"
