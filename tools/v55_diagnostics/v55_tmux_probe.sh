#!/usr/bin/env bash
# Diagnose the tmux on this host: version, socket support, and the exact
# new-session syntax that works.
WS=/data/raw/huzijian/project1_database
SOCK="$WS/tmp/tmux_v55.sock"

echo "=== tmux version ==="
tmux -V

echo
echo "=== does it accept -S (separate socket)? ==="
tmux -S "$SOCK" ls 2>&1 | head -3

echo
echo "=== try: new-session -d -s NAME <cmd> ==="
tmux -S "$SOCK" new-session -d -s probe_a /bin/echo hello 2>&1
echo "rc=$?"
tmux -S "$SOCK" ls 2>&1 | head -3

echo
echo "=== try with an explicit shell wrapper ==="
tmux -S "$SOCK" new-session -d -s probe_b /bin/bash -c 'echo hi > /tmp/x' 2>&1
echo "rc=$?"

echo
echo "=== try a plain single-token command ==="
tmux -S "$SOCK" new-session -d -s probe_c /bin/sleep 5 2>&1
echo "rc=$?"

echo
echo "=== sessions now ==="
tmux -S "$SOCK" ls 2>&1

echo
echo "=== what shell/tmux binary ==="
ls -la "$(command -v tmux)"
