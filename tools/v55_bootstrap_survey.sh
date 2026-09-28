#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01 bootstrap -- READ-ONLY takeover survey.
#
# Writes a report under the project workspace; deletes nothing.
# Per 01_operations.md section 4/6: inventory, resource state, boundary checks,
# and the state of the previously-interrupted upload.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
WS=/data/raw/huzijian/project1_database
cd "$WS" || exit 1
OUT="$WS/outcomes/v55/bootstrap"
RUN_ID="${RUN_ID:-$(date +%Y%m%dT%H%M%S)}"
mkdir -p "$OUT/$RUN_ID" "$WS/tmp" "$WS/remove"

echo "=== A. identity / time ==="
echo "RUN_ID    = $RUN_ID"
echo "host      = $(hostname)"
echo "user      = $(whoami)"
echo "date      = $(date -Is)"
echo "kernel    = $(uname -r)"
echo "cwd       = $(pwd)"

echo
echo "=== B. workspace boundary ==="
echo "WS exists = $([ -d "$WS" ] && echo YES || echo NO)"
echo "WS realpath = $(readlink -f "$WS")"
for d in tmp remove outcomes outcomes/v55 tools code models datasets; do
  printf '  %-14s %s\n' "$d" "$([ -e "$WS/$d" ] && echo EXISTS || echo MISSING)"
done

echo
echo "=== C. runtimes (project-side only) ==="
PY="$WS/tools/conda_env/bin/python"
echo "conda python: $([ -x "$PY" ] && echo "$PY" || echo MISSING)"
[ -x "$PY" ] && "$PY" -VV 2>&1 | sed 's/^/  /'
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
echo "server blender: $([ -x "$BL" ] && echo "$BL" || echo MISSING)"
[ -x "$BL" ] && "$BL" --version 2>&1 | head -2 | sed 's/^/  /'
echo "system python3: $(command -v python3 || echo none) ($(python3 -V 2>&1))"
echo "tmux: $(command -v tmux || echo MISSING)"
echo "ffmpeg: $(command -v ffmpeg || echo MISSING)"

echo
echo "=== D. previously-interrupted upload: v54_init_remove.sh ==="
F="$WS/tools/v54_init_remove.sh"
if [ -f "$F" ]; then
  echo "EXISTS  $F"
  echo "  size   = $(stat -c%s "$F")"
  echo "  mtime  = $(stat -c%y "$F")"
  echo "  sha256 = $(sha256sum "$F" | cut -d' ' -f1)"
else
  echo "ABSENT  $F  -> upload was interrupted before landing (as the plan warned)"
fi

echo
echo "=== E. remove directory (server side) ==="
R="$WS/remove"
mkdir -p "$R" && echo "mkdir -p OK" || echo "mkdir FAILED"
echo "stat: $(stat -c 'type=%F mode=%A owner=%U:%G mtime=%y' "$R" 2>&1)"
echo "readlink -f: $(readlink -f "$R")"

echo
echo "=== F. existing project tmux sessions ==="
tmux ls 2>&1 | sed 's/^/  /' || echo "  (no default-socket sessions)"
echo "--- our own socket ---"
SOCK="$WS/tmp/tmux_v55.sock"
tmux -S "$SOCK" ls 2>&1 | sed 's/^/  /' || echo "  (socket not created yet)"

echo
echo "=== G. git state ==="
if [ -d .git ]; then
  echo "HEAD   = $(git rev-parse HEAD 2>&1)"
  echo "branch = $(git rev-parse --abbrev-ref HEAD 2>&1)"
  echo "remote = $(git remote get-url origin 2>&1)"
  echo "--- status --short (first 20) ---"
  git status --short 2>&1 | head -20 | sed 's/^/  /'
else
  echo "no .git in $WS"
fi

echo
echo "=== H. disk / resources ==="
df -h "$WS" 2>&1 | sed 's/^/  /'
echo "--- memory ---"
free -g 2>&1 | sed 's/^/  /'
echo "--- cpu ---"
nproc 2>&1 | sed 's/^/  cores=/'

echo
echo "=== I. DONE ==="
echo "report dir: $OUT/$RUN_ID"
