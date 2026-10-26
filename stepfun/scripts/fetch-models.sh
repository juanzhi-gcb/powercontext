#!/bin/sh
# Fetch the embedding model so the browser can load it from this server instead of a
# remote host. Keeping the weights local makes repeated benchmark runs deterministic and
# lets the app work offline. The files are ignored by git.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${MODEL_ID:-Xenova/all-MiniLM-L6-v2}"
BASE="${HF_BASE:-https://huggingface.co/$MODEL/resolve/main}"
DEST="$ROOT/public/models/$MODEL"

mkdir -p "$DEST/onnx"

fetch() {
  path="$1"
  if [ -s "$DEST/$path" ]; then
    echo "skip $path"
    return
  fi
  echo "fetch $path"
  curl -fL --retry 3 --retry-delay 2 -o "$DEST/$path" "$BASE/$path"
}

fetch config.json
fetch tokenizer.json
fetch tokenizer_config.json
fetch onnx/model_quantized.onnx
fetch onnx/model.onnx

echo "models ready in $DEST"
du -sh "$DEST"