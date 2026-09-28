#!/usr/bin/env bash
# Build the V5.5 stage-01 local evidence bundle (disk copy of server evidence).
#
# Copies into outcomes/v55/bootstrap/<run_id>/ the raw server logs, so the local
# delivery in section 09 has the evidence alongside the code.  Copies only; no
# deletion, and no overwriting of an existing file with the same name.
WS=/data/raw/huzijian/project1_database
OUT="$WS/outcomes/v55/bootstrap/20260928T194500"
mkdir -p "$OUT"

copy() {
  local src="$1" dst="$2"
  if [ -f "$src" ]; then
    if [ -f "$dst" ]; then
      echo "  SKIP (exists): $dst"
    else
      cp -p "$src" "$dst" && echo "  copied: $(basename "$dst")"
    fi
  else
    echo "  MISSING src: $src"
  fi
}

echo "=== gathering stage-01 evidence into $OUT ==="
copy "$WS/tmp/v55_survey.log"                    "$OUT/01_survey.log"
copy "$WS/tmp/v55_bootstrap_01.out"              "$OUT/01_verify_tmux.log"
copy "$WS/tmp/v55_bootstrap_01.rc"               "$OUT/01_verify_tmux.rc"
copy "$WS/tmp/v55_render_reg2.out"               "$OUT/01_render_regression_tmux.log"
copy "$WS/tmp/v55_render_reg2.rc"                "$OUT/01_render_regression_tmux.rc"
copy "$WS/tmp/v55_del.log"                       "$OUT/01_delete_audit_grep.log"
copy "$WS/tmp/v55_purge.log"                     "$OUT/01_purge_callsite.log"
copy "$WS/tmp/v55_scratch.log"                   "$OUT/01_scratch_alloc.log"
copy "$WS/tmp/v55_blender_probe.log"             "$OUT/01_blender_probe.log"

echo
echo "=== AST audit + regressions re-run, captured to files ==="
cd "$WS/code/physics-video-sim/physics-video-sim-main" || exit 1
"$WS/tools/conda_env/bin/python" "$WS/tools/v55_ast_delete_audit.py" src scripts \
  > "$OUT/01_ast_delete_audit.log" 2>&1
echo "  ast audit rc=$? -> 01_ast_delete_audit.log"

"$WS/tools/conda_env/bin/python" "$WS/tools/v55_test_no_delete.py" \
  > "$OUT/01_no_delete_proof.log" 2>&1
echo "  no-delete proof rc=$? -> 01_no_delete_proof.log"
tail -1 "$OUT/01_no_delete_proof.log" | sed 's/^/    /'

bash "$WS/tools/v55_regression_existing.sh" > "$OUT/01_regression_existing.log" 2>&1
echo "  existing regression rc=$? -> 01_regression_existing.log"
grep -E 'RESULT:' "$OUT/01_regression_existing.log" | sed 's/^/    /'

echo
echo "=== final listing ==="
ls -la "$OUT" | sed 's/^/  /'
echo
echo "=== quarantine evidence (remove/) ==="
find "$WS/remove" -name 'move_manifest.json' | sed 's/^/  /'
echo "  total quarantined files: $(find "$WS/remove" -type f | wc -l)"
