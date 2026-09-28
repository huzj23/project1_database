#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01: understand the ONLY automatic-deletion call in the live chain and
# how the scratch directory that feeds it is allocated.
# READ-ONLY.
# ===========================================================================
export LC_ALL=C
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== A. blender_backend.py lines 100-130 (the purge call site) ==="
sed -n '100,130p' src/physim/render/blender_backend.py | cat -n | sed 's/^/  /'

echo
echo "=== B. the other two 'unlink' hits: are they FILE deletes or Blender object unlinks? ==="
echo "--- preview.py around line 25 ---"
sed -n '15,32p' src/physim/preview.py | cat -n | sed 's/^/  /'
echo "--- reference.py around line 36 ---"
sed -n '25,45p' src/physim/reference.py | cat -n | sed 's/^/  /'

echo
echo "=== C. how does pipeline.py allocate the scratch dir? ==="
grep -n 'scratch\|PhyCoBlenderBackend\|mkdtemp\|out_dir\|output' src/physim/pipeline.py | sed 's/^/  /'

echo
echo "=== D. pipeline.py: the render invocation region ==="
grep -n 'PhyCoBlenderBackend(' -B 12 -A 8 src/physim/pipeline.py | sed 's/^/  /'
