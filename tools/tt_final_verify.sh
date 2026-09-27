#!/usr/bin/env bash
# ===========================================================================
# FINAL verification on the frozen file state, run sequentially:
#   1. disc material measurement (real build_scene render, 8 samples)
#   2. preflight_full3.sh (14 non-turntable cases)
# No two Blender renders run at once.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
W="$WS"

echo "##################### FINAL FILE MANIFEST #####################"
cd "$W/code/physics-video-sim/physics-video-sim-main" || exit 1
md5sum \
  src/physim/assets/__init__.py \
  src/physim/render/materials.py \
  src/physim/render/blender_backend.py \
  src/physim/scenarios/__init__.py \
  src/physim/scenarios/turntable.py \
  assets/objects/turntable/asset.yaml \
  assets/objects/turntable/visual/model.obj \
  assets/objects/turntable/visual/model.obj.nomtl-bak \
  assets/objects/turntable/visual/model.mtl \
  assets/objects/turntable/visual/model.mtl.nomtl-bak \
  scripts/export_preview_simulation.py

echo "##################### 1. DISC MATERIAL MEASUREMENT #####################"
bash "$W/tools/tt_material_probe.sh" 2>&1 | grep -E '^MM (RESULT disc|manifest|sample)'

echo "##################### 2. PREFLIGHT (non-turntable scenarios) #####################"
bash "$W/tools/preflight_full3.sh" 2>&1 | grep -E '^TOTAL|FAIL|ERROR'

echo "##################### 3. SAVED ARTIFACTS #####################"
ls -la "$W/outcomes/_tt_mat/" | grep -E 'MPROBE|ACTOR'
echo "FINAL_DONE"
