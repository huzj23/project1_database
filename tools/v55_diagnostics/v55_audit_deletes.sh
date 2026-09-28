#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01 section 5 -- find every automatic-deletion path in the code that
# the pipeline ACTUALLY calls (not every historical script).
# READ-ONLY: only greps and reads.
# ===========================================================================
export LC_ALL=C
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== A. delete primitives in the LIVE package (src/) ==="
grep -rn 'unlink\|rmtree\|os\.remove\|os\.rmdir\|shutil\.rmtree\|TemporaryDirectory\|mkdtemp\|NamedTemporary' src/ \
  | sed 's/^/  /'

echo
echo "=== B. purge_stale_frames: exact definition ==="
grep -n 'def purge_stale_frames' -A 40 src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== C. who calls purge_stale_frames? ==="
grep -rn 'purge_stale_frames' src/ scripts/ tools/ 2>/dev/null | sed 's/^/  /'

echo
echo "=== D. delete primitives in scripts/ and tools/ (pipeline entry points) ==="
grep -rn 'unlink\|rmtree\|os\.remove\|shutil\.rmtree' scripts/ 2>/dev/null | sed 's/^/  /'

echo
echo "=== E. TemporaryDirectory / mkdtemp in src/ (auto-cleaning temp dirs) ==="
grep -rn 'TemporaryDirectory\|mkdtemp' src/ | sed 's/^/  /'

echo
echo "=== F. the pipeline entry point (generate.py) output handling ==="
ls scripts/ | sed 's/^/  /'
