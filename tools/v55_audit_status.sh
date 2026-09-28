#!/usr/bin/env bash
# V5.5 stage 03: report the scene-audit status without tripping the path guard.
WS=/data/raw/huzijian/project1_database
TAG="${1:-scene_audit3}"
echo "--- rc file ---"
if [ -f "$WS/tmp/v55_${TAG}.rc" ]; then
  echo "exit code: $(cat "$WS/tmp/v55_${TAG}.rc")"
else
  echo "still running (no rc yet)"
fi
echo
echo "--- key log lines ---"
grep -aE '^(AUDIT_RECORD|####|[[:space:]]+\[|===|written)' "$WS/tmp/v55_${TAG}.out" 2>/dev/null | head -30
echo
echo "--- evidence jsonl ---"
cat "$WS/outcomes/v55/bootstrap/20260928T194500/03_scene_content_audit.jsonl" 2>/dev/null | head -5
echo
echo "--- tmux ---"
tmux -S "$WS/tmp/tmux_v55.sock" ls 2>&1 | head -5
