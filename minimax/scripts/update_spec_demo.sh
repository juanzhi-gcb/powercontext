#!/usr/bin/env bash
# Prove the context is computed from the database, not hard-coded:
# append a sentence to SPEC-ORD-003 R1, re-import, and show the new requirement
# text plus the bumped revision in the selected context. The specification is
# restored at the end.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
PY=".venv/bin/python"
SPEC="specs/SPEC-ORD-003-min-total.md"
BACKUP=".runtime/SPEC-ORD-003-min-total.md.bak"
TASK_FILE="tasks/TASK-ORD-003.md"

mkdir -p .runtime
cp "$SPEC" "$BACKUP"
trap 'cp "$BACKUP" "$SPEC"; $PY -m sdd_context.cli ingest >/dev/null' EXIT

echo "== context before the specification update =="
$PY -m sdd_context.cli context --task-file "$TASK_FILE" --out .runtime/context-before.json >/dev/null
$PY - <<'PY'
import json
ctx = json.load(open(".runtime/context-before.json"))
item = next(i for i in ctx["spec_items"] if i["id"] == "SPEC-ORD-003#R1")
print("revision:", item["source"]["revision"])
print("requirement:", item["requirement"].splitlines()[-1])
PY

echo "== append a new rule to SPEC-ORD-003 R1 =="
PATCH_LINE='示例变更新增：`min_total` 允许带千分位分隔符（例如 `"1,500.00"`），解析前必须先去掉逗号。'
# insert right after the R1 paragraph (before "## R2")
awk -v line="$PATCH_LINE" '
  /^## R2 / && !done { print ""; print line; done=1 }
  { print }
' "$SPEC" > "$SPEC.tmp" && mv "$SPEC.tmp" "$SPEC"

$PY -m sdd_context.cli ingest

echo "== context after re-import =="
$PY -m sdd_context.cli context --task-file "$TASK_FILE" --out .runtime/context-after.json >/dev/null
$PY - <<'PY'
import json
before = json.load(open(".runtime/context-before.json"))
after = json.load(open(".runtime/context-after.json"))
b = next(i for i in before["spec_items"] if i["id"] == "SPEC-ORD-003#R1")
a = next(i for i in after["spec_items"] if i["id"] == "SPEC-ORD-003#R1")
print("revision:", b["source"]["revision"], "->", a["source"]["revision"])
print("requirement now ends with:", a["requirement"].splitlines()[-1])
assert b["requirement"] != a["requirement"], "context did not change"
print("OK: the context follows the updated specification")
PY

echo "specification restored on exit"
