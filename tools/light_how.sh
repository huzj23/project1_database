#!/usr/bin/env bash
# ===========================================================================
# How is the authored lighting SUPPOSED to reach the renderer?
#
# asset.yaml says:
#     render:
#       lighting_source: authored_config_only
#       authored_config: configs/lighting/frl_apartment_stage.lighting_config.json
#
# so there is an explicit authored config file.  Establish:
#   1. does that JSON exist, and what does it contain?
#   2. does blender_backend consume `authored_config` at all, or only the blend's
#      `environment_lighting` collection?
#   3. what does prepare_visual_asset.py do to produce the expected names?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1) the lighting config files ==="
ls -la configs/lighting/ 2>/dev/null | sed 's/^/  /'
echo "  --- frl_apartment_stage.lighting_config.json ---"
head -c 1200 configs/lighting/frl_apartment_stage.lighting_config.json 2>/dev/null | sed 's/^/  /'
echo

echo "=== 2) does blender_backend read authored_config / lighting_source? ==="
grep -n 'authored_config\|lighting_source\|supplemental_lights\|area_lights' \
  src/physim/render/blender_backend.py | sed 's/^/  /'
echo "  --- where environment_render comes from ---"
grep -n 'environment_render' src/physim/render/blender_backend.py | head | sed 's/^/  /'

echo
echo "=== 3) prepare_visual_asset.py: the normalization it performs ==="
sed -n '135,175p' scripts/prepare_visual_asset.py | sed 's/^/  /'
echo "  --- LIGHTING_COLLECTION_NAME usage ---"
grep -n 'LIGHTING_COLLECTION_NAME\|WORLD_NAME' scripts/prepare_visual_asset.py | sed 's/^/  /'
