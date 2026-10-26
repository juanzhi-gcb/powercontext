#!/bin/sh
# Run a Node entry point with the seekdb native library preloaded.
#
# On Linux the embedded runtime is shipped as a shared object that reserves a large
# static TLS block. Node's dlopen path cannot satisfy that reservation, so the library
# has to be present when the process starts (LD_PRELOAD). The bindings download the
# library on first use, so this script waits for it to appear before exec'ing Node.
set -eu

CACHE="${SEEKDB_BINDINGS_HOME:-$HOME/.seekdb}"

find_library() {
  find "$CACHE" -name 'libseekdb.so' -type f 2>/dev/null | head -n 1
}

LIBRARY="$(find_library)"
if [ -z "$LIBRARY" ]; then
  echo "seekdb native library not found under $CACHE; run 'npm run dev:server' once so the bindings download it" >&2
  exec node "$@"
fi

LD_PRELOAD="$LIBRARY${LD_PRELOAD:+:$LD_PRELOAD}"
export LD_PRELOAD
exec node "$@"