#!/usr/bin/env bash
# Test-run the project's collision generator into scratch space (no asset touched).
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
mkdir -p "$WS/tmp/zz_coll_test"
"$BLENDER" --background --factory-startup --python scripts/generate_collision_mesh.py -- \
  --source assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj \
  --output "$WS/tmp/zz_coll_test/model.obj" \
  --urdf-output "$WS/tmp/zz_coll_test/model.urdf" \
  --target-faces 512 \
  --report "$WS/tmp/zz_coll_test/report.json" 2>&1
echo "BLENDER_EXIT=$?"
echo "=== report.json ==="
cat "$WS/tmp/zz_coll_test/report.json"
