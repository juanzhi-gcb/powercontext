#!/bin/sh
# Fetch the seekdb native runtime into the SDK's cache directory.
#
# The npm package ships no native code: @seekdb/js-bindings downloads a ~54 MB archive
# from AWS on first use. That download has no timeout, no progress and no retry, and on a
# slow link it stalls a few megabytes in and never finishes, leaving the server hanging
# with no output at all. This script performs the same download with curl, so it can be
# resumed, bounded in time and reported, then unpacks it where the SDK looks for it
# (<cache>/<commit>/<platform>/seekdb.node).
#
# Overrides:
#   SEEKDB_BINDINGS_BASE_URL    mirror serving the same archive layout
#   SEEKDB_BINDINGS_CACHE_DIR   cache root (default ~/.seekdb/bindings)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BINDINGS_DIR="$ROOT/node_modules/@seekdb/js-bindings"

if [ ! -f "$BINDINGS_DIR/download.js" ]; then
  echo "missing $BINDINGS_DIR; run 'npm install' first" >&2
  exit 1
fi

# The SDK pins the runtime to a build commit; read it from the installed package so the
# download cannot drift from what the loader expects.
COMMIT=$(sed -n 's#.*all_commits/\([0-9a-f]\{7,40\}\).*#\1#p' "$BINDINGS_DIR/download.js" | head -n 1)
if [ -z "$COMMIT" ]; then
  echo "cannot read the bindings commit from $BINDINGS_DIR/download.js" >&2
  exit 1
fi

PLATFORM=$(node -p "process.platform + '-' + (process.arch === 'arm64' ? 'arm64' : 'x64')")
BASE=${SEEKDB_BINDINGS_BASE_URL:-https://oceanbase-seekdb-builds.s3.ap-southeast-1.amazonaws.com/js-bindings/all_commits/$COMMIT}
CACHE=${SEEKDB_BINDINGS_CACHE_DIR:-$HOME/.seekdb/bindings}
TARGET="$CACHE/$COMMIT/$PLATFORM"
ARCHIVE="$TARGET/seekdb-js-bindings-$PLATFORM.zip"

if [ -f "$TARGET/seekdb.node" ]; then
  echo "seekdb runtime already present: $TARGET" >&2
  exit 0
fi

mkdir -p "$TARGET"

echo "fetching seekdb runtime for $PLATFORM (~54 MB, resumable)…" >&2
# -C - resumes a partial archive instead of starting over; the retries keep a transient
# reset part-way through from throwing away what was already transferred.
if ! curl -fL --retry 5 --retry-delay 3 --retry-all-errors \
     --connect-timeout 20 --max-time 1800 -C - \
     -o "$ARCHIVE" "$BASE/seekdb-js-bindings-$PLATFORM.zip"; then
  echo "download failed: $BASE/seekdb-js-bindings-$PLATFORM.zip" >&2
  echo "the partial archive is kept at $ARCHIVE so a retry resumes it;" >&2
  echo "set SEEKDB_BINDINGS_BASE_URL to use a mirror instead" >&2
  exit 1
fi

if command -v unzip >/dev/null 2>&1; then
  unzip -o -q "$ARCHIVE" -d "$TARGET"
else
  node -e 'new (require(process.argv[1] + "/adm-zip"))(process.argv[2]).extractAllTo(process.argv[3], true)' \
    "$ROOT/node_modules" "$ARCHIVE" "$TARGET"
fi

if [ ! -f "$TARGET/seekdb.node" ]; then
  echo "archive did not contain seekdb.node: $ARCHIVE" >&2
  exit 1
fi

rm -f "$ARCHIVE"
echo "seekdb runtime ready: $TARGET" >&2