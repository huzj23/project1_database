#!/usr/bin/env bash
# Control experiment: run the project generator on food_lime (GLB, already
# conformant) and compare with its COMMITTED collision mesh.
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
mkdir -p "$WS/tmp/zz_ctrl_lime"
"$BLENDER" --background --factory-startup --python scripts/generate_collision_mesh.py -- \
  --source assets/objects/food_lime/visual/model.glb \
  --output "$WS/tmp/zz_ctrl_lime/model.obj" \
  --urdf-output "$WS/tmp/zz_ctrl_lime/model.urdf" \
  --target-faces 512 \
  --report "$WS/tmp/zz_ctrl_lime/report.json" > "$WS/tmp/zz_ctrl_lime/blender.log" 2>&1
echo "BLENDER_EXIT=$?"
grep -E 'COLLISION_REPORT|Error|Traceback' "$WS/tmp/zz_ctrl_lime/blender.log" | head -5
echo "=== report ==="
cat "$WS/tmp/zz_ctrl_lime/report.json"
echo
echo "=== sha256: generated vs committed ==="
sha256sum "$WS/tmp/zz_ctrl_lime/model.obj" assets/objects/food_lime/collision/model.obj
echo "=== byte diff size ==="
wc -c "$WS/tmp/zz_ctrl_lime/model.obj" assets/objects/food_lime/collision/model.obj
