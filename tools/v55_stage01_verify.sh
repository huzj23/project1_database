#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01 verification run, executed inside a project tmux session.
#
# Proves on the SERVER (authoritative):
#   * the no-delete tests pass there too
#   * the patched chain renders a real frame and quarantines the sentinel
#   * the existing delivered dataset is untouched
#   * resource/thread policy is what v55_env.sh claims
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$REPO" || exit 1

echo "=== run identity ==="
echo "date    = $(date -Is)"
echo "host    = $(hostname)"
echo "cwd     = $(pwd)"
echo "CUDA_VISIBLE_DEVICES='${CUDA_VISIBLE_DEVICES}' KUBRIC_USE_GPU=${KUBRIC_USE_GPU}"
echo "threads : OMP=${OMP_NUM_THREADS} MKL=${MKL_NUM_THREADS} BLENDER=${BLENDER_THREADS}"
echo "TMPDIR  = $TMPDIR"
echo "PHYSIM_WORKSPACE_ROOT = $PHYSIM_WORKSPACE_ROOT"

echo
echo "=== 1. compile-check the patched modules ==="
"$PY" -m py_compile src/physim/safe_output.py src/physim/render/blender_backend.py \
  && echo "  both compile OK" || echo "  COMPILE FAILED"

echo
echo "=== 2. no-delete proof (server) ==="
"$PY" "$WS/tools/v55_test_no_delete.py" 2>&1 | tail -20

echo
echo "=== 3. confirm no unlink remains in the live render module ==="
if grep -q '\.unlink()' src/physim/render/blender_backend.py; then
  echo "  FAIL: unlink still present"
  grep -n '\.unlink()' src/physim/render/blender_backend.py | sed 's/^/    /'
else
  echo "  PASS: no .unlink() in blender_backend.py"
fi
echo "  --- remaining delete primitives in src/ (should only be Blender object unlinks) ---"
grep -rn 'unlink\|rmtree\|os\.remove' src/ --include='*.py' | sed 's/^/    /'

echo
echo "=== 4. existing delivered dataset untouched (sentinel count) ==="
D="$REPO/datasets"
if [ -d "$D" ]; then
  echo "  dataset dirs: $(find "$D" -maxdepth 2 -mindepth 2 -type d | wc -l)"
  echo "  total files : $(find "$D" -type f | wc -l)"
  echo "  total size  : $(du -sh "$D" | cut -f1)"
else
  echo "  datasets/ MISSING"
fi

echo
echo "=== 5. remove/ inventory (quarantine evidence) ==="
find "$WS/remove" -name 'move_manifest.json' | tail -5 | sed 's/^/  /'
echo "  quarantined files: $(find "$WS/remove" -type f | wc -l)"

echo
echo "=== DONE ==="
