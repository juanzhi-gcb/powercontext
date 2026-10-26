#!/usr/bin/env bash
# Create the virtualenv and install the pinned runtime.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
INDEX_ARGS=()
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  INDEX_ARGS=(--index-url "$PIP_INDEX_URL")
fi

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV_BIN="${HOME}/.local/bin/uv"
fi

if [[ ! -x .venv/bin/python ]]; then
  if [[ -n "$UV_BIN" ]]; then
    # uv can fetch a managed CPython when the system one lacks venv support.
    "$UV_BIN" venv --python "${SDDCTX_PYTHON:-3.12}" .venv
  else
    if ! "$PYTHON_BIN" -m venv .venv; then
      echo "python3 -m venv failed." >&2
      echo "Install python3-venv (Debian/Ubuntu) or uv (https://docs.astral.sh/uv/), then retry." >&2
      exit 1
    fi
  fi
fi

if [[ -n "$UV_BIN" ]]; then
  "$UV_BIN" pip install --python .venv/bin/python "${INDEX_ARGS[@]}" -r requirements.txt
else
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install "${INDEX_ARGS[@]}" -r requirements.txt
fi

echo "virtualenv ready: $PWD/.venv"
echo "python: $(.venv/bin/python -V)"