#!/bin/sh
# Run a Node entry point with the seekdb native library preloaded.
#
# On Linux the embedded runtime is shipped as a shared object that reserves a large
# static TLS block. Node's dlopen path cannot satisfy that reservation, so the library
# has to be present when the process starts (LD_PRELOAD).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
CACHE=${SEEKDB_BINDINGS_CACHE_DIR:-$HOME/.seekdb/bindings}

find_library() {
  find "$CACHE" -name 'libseekdb.so' -type f 2>/dev/null | head -n 1
}

LIBRARY=$(find_library)
if [ -z "$LIBRARY" ]; then
  # Fresh clone: the runtime is not part of the npm package. Fetch it here, with a
  # timeout and progress, instead of leaving node to hang inside the SDK's downloader.
  sh "$HERE/ensure-bindings.sh"
  LIBRARY=$(find_library)
fi

if [ -z "$LIBRARY" ]; then
  echo "seekdb runtime missing: no libseekdb.so under $CACHE" >&2
  echo "run 'npm run setup' to fetch it, or point SEEKDB_BINDINGS_CACHE_DIR at an existing cache" >&2
  exit 1
fi

# Ubuntu 24.04+ ships libaio as libaio.so.1t64 only; without the compatibility link
# ld.so fails with a bare "cannot open shared object file" that says nothing about the fix.
if command -v ldd >/dev/null 2>&1; then
  MISSING=$(ldd "$LIBRARY" 2>/dev/null | awk '/not found/ {print $1}' | tr '\n' ' ' || true)
  if [ -n "${MISSING:-}" ]; then
    echo "seekdb runtime cannot load; missing shared libraries: $MISSING" >&2
    case " $MISSING " in
      *" libaio.so.1 "*)
        echo "Ubuntu 24.04+ ships libaio as libaio.so.1t64; add the compatibility link:" >&2
        echo "  sudo apt-get install -y libaio1t64" >&2
        echo "  sudo ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1" >&2
        echo "  sudo ldconfig" >&2
        ;;
      *)
        echo "the runtime archive may be incomplete; re-run 'npm run setup'" >&2
        ;;
    esac
    exit 1
  fi
fi

LD_PRELOAD="$LIBRARY${LD_PRELOAD:+:$LD_PRELOAD}"
export LD_PRELOAD
exec node "$@"