#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01: prove the PATCHED render chain still works end-to-end and that it
# quarantines instead of deleting.
#
# Uses the real server Blender (3.4.1).  The earlier survey showed that binary is
# missing libxkbcommon.so.0 from the system; this script first checks whether the
# project's own runtime/lib directory supplies it before giving up.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$REPO" || exit 1

echo "=== A. can this Blender run at all? ==="
echo "BLENDER=$BLENDER"
if "$BLENDER" --version >/dev/null 2>&1; then
  echo "  plain launch: OK -> $("$BLENDER" --version 2>&1 | head -1)"
else
  echo "  plain launch FAILED:"
  "$BLENDER" --version 2>&1 | head -3 | sed 's/^/    /'
  echo "  --- retrying with the project runtime/lib on LD_LIBRARY_PATH ---"
  export LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}"
  if "$BLENDER" --version >/dev/null 2>&1; then
    echo "  with runtime/lib: OK -> $("$BLENDER" --version 2>&1 | head -1)"
  else
    echo "  with runtime/lib: STILL FAILED:"
    "$BLENDER" --version 2>&1 | head -3 | sed 's/^/    /'
    echo
    echo "  --- what is in runtime/lib? ---"
    ls "$WS/tools/runtime/lib" 2>&1 | head -20 | sed 's/^/    /'
    echo
    echo "  --- is libxkbcommon available anywhere in the workspace? ---"
    find "$WS" -name 'libxkbcommon*' 2>/dev/null | head -5 | sed 's/^/    /'
    echo
    echo "  => server-side Blender is unusable for rendering on this host."
    echo "     This confirms 01/09's warning; local Blender 4.2 is the render route."
  fi
fi
