#!/usr/bin/env bash
# Probe whether a tmux server socket can live inside the workspace (V5.6 section 9).
#
# Why this matters: V5.6 section 9 forbids project sockets, caches and outputs outside the workspace,
# and records that an earlier V5.5 probe put its socket in WSL /tmp, which is a violation to be
# reported rather than repeated. The section names /mnt/d/workspace/project1_database/tmp/... as the
# path to try. WSL's /mnt/d is a 9p/DrvFs mount to the Windows drive, and Unix domain sockets are
# NOT supported on every such mount, so this has to be tested rather than assumed.
#
# Reported as: SUPPORTED / NOT_SUPPORTED, with the exact error. No fallback outside the workspace.

set -u

WS="/mnt/d/workspace/project1_database"
DIR="$WS/tmp/v56_tmux_probe"
SOCK="$DIR/probe.sock"

echo "=== V5.6 section 9: tmux socket inside the workspace ==="
echo "workspace : $WS"
echo "socket    : $SOCK"
echo "tmux      : $(command -v tmux || echo MISSING)"
tmux -V 2>&1

mkdir -p "$DIR" || { echo "RESULT: NOT_SUPPORTED (cannot create $DIR)"; exit 2; }
echo "dir created: yes"

# Remove any stale socket PATH only. This probe owns its own directory and its own socket file; it
# is not touching project data. A socket file is not a project artifact and cannot be archived.
if [ -S "$SOCK" ]; then
  rm -f "$SOCK"
  echo "removed stale probe socket (this probe's own socket file, not project data)"
fi

OUT="$(tmux -S "$SOCK" new-session -d -s v56probe "sleep 60" 2>&1)"
RC=$?
echo "new-session rc=$RC out=[$OUT]"

if [ $RC -ne 0 ]; then
  echo "RESULT: NOT_SUPPORTED"
  echo "  tmux could not create a server socket at $SOCK"
  echo "  error: $OUT"
  echo "  NOTE: /mnt/d is a 9p/DrvFs mount; Unix domain sockets are not supported on all such mounts."
  echo "  Per section 9 this is reported as an execution-boundary blocker rather than worked around"
  echo "  by writing outside the workspace."
  exit 3
fi

LS="$(tmux -S "$SOCK" ls 2>&1)"
echo "ls: $LS"
if [ -S "$SOCK" ]; then
  echo "socket file exists: yes ($(stat -c '%s bytes, mode %a' "$SOCK"))"
else
  echo "socket file exists: NO (tmux reported success but no socket file is present)"
fi

# Prove a command can actually be sent and its output retrieved: creating a server is not the same
# as being able to drive it, and a session that cannot run a command is not usable.
tmux -S "$SOCK" send-keys -t v56probe "echo PROBE_OK_42 > $DIR/probe_out.txt" C-m 2>&1
sleep 2
if [ -f "$DIR/probe_out.txt" ]; then
  echo "command round-trip: $(cat "$DIR/probe_out.txt")"
  echo "RESULT: SUPPORTED"
else
  echo "command round-trip: FAILED (no output file)"
  echo "RESULT: NOT_SUPPORTED (server starts but cannot execute a command)"
fi

tmux -S "$SOCK" kill-server 2>&1
echo "server killed: rc=$?"
echo "=== end probe ==="
