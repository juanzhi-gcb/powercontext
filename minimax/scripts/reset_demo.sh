#!/usr/bin/env bash
# Restore demo_project to the committed pre-change snapshot.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
.venv/bin/python -m sdd_context.cli reset-demo