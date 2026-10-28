#!/bin/sh
# Fetch the embedding model so the browser can load it from this server instead of a
# remote host. Keeping the weights local makes repeated benchmark runs deterministic and
# lets the app work offline. The files are ignored by git.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL=$(node -p 'require(process.argv[1]).id' "$ROOT/model.json")
REVISION=$(node -p 'require(process.argv[1]).revision' "$ROOT/model.json")
BASE="${HF_BASE:-https://huggingface.co/$MODEL/resolve/$REVISION}"
DEST="$ROOT/public/models/$MODEL"

mkdir -p "$DEST/onnx"

verify() {
  node - "$ROOT/model.json" "$DEST" "$1" <<'NODE'
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const [manifest, dest, name] = process.argv.slice(2);
const file = path.join(dest, name);
if (!fs.existsSync(file) || fs.statSync(file).size === 0) process.exit(1);
const expected = Object.values(require(manifest).onnx).find(item => name === `onnx/${item.file}`);
if (expected) {
  const bytes = fs.readFileSync(file);
  const hash = crypto.createHash('sha256').update(bytes).digest('hex');
  if (bytes.length !== expected.bytes || hash !== expected.sha256) process.exit(1);
} else {
  try { JSON.parse(fs.readFileSync(file, 'utf8')); } catch { process.exit(1); }
}
NODE
}

fetch() {
  path="$1"
  if verify "$path"; then
    echo "verified $path"
    return
  fi
  echo "fetch $path"
  curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 900 \
    -o "$DEST/$path.part" "$BASE/$path"
  mv "$DEST/$path.part" "$DEST/$path"
  if ! verify "$path"; then
    echo "model verification failed: $path ($REVISION)" >&2
    exit 1
  fi
}

fetch config.json
fetch tokenizer.json
fetch tokenizer_config.json
fetch onnx/model_quantized.onnx
fetch onnx/model.onnx
# fp16 is the fastest precision on WebGPU for this model; the benchmark compares it with int8.
fetch onnx/model_fp16.onnx

echo "models ready in $DEST (revision $REVISION)"
du -sh "$DEST"
