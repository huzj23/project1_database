#!/usr/bin/env bash
# Tidy the V5.5 tools: keep repeatable pipeline entry points at tools/ top level and
# move one-off diagnostic probes into tools/v55_diagnostics/.
#
# MOVES only -- nothing is deleted, and an existing destination is never overwritten.
WS=/data/raw/huzijian/project1_database
T="$WS/tools"
D="$T/v55_diagnostics"
mkdir -p "$D"

# One-off diagnostics used during stage 01 investigation.
DIAG="v55_tmux_probe.sh v55_tmux_probe2.sh v55_tmux_probe3.sh v55_tree_layout.sh
      v55_vendor_check.sh v55_vendor_git.sh v55_audit_deletes.sh v55_audit_purge.sh
      v55_audit_scratch.sh v55_classify_inventory.py v55_split_diff.py"

for f in $DIAG; do
  if [ -f "$T/$f" ]; then
    if [ -e "$D/$f" ]; then
      echo "  SKIP (dest exists): $f"
    else
      mv "$T/$f" "$D/$f" && echo "  moved: $f -> v55_diagnostics/"
    fi
  else
    echo "  absent: $f"
  fi
done

echo
echo "=== tools/ top-level V5.5 entry points ==="
ls "$T"/v55_* 2>/dev/null | sed 's|.*/|  |'
echo
echo "=== tools/v55_diagnostics/ ==="
ls "$D" | sed 's/^/  /'
