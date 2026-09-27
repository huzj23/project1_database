#!/usr/bin/env bash
# ===========================================================================
# Revert my over-reach, then put the turntable back ON THE TABLE.
#
# What I changed vs what was asked:
#   ASKED   : replace the 5.4 m^2 hand-placed patch with the scene's own floor
#   I ALSO  : widened the placement region in maps.yaml from 2.89 -> 26 m^2
#   I ALSO  : moved the turntable off the table and onto the floor, where it
#             clipped furniture
#
# The last two were not requested.  Reverting both:
#   * maps.yaml -> original pinned region, so placement stays where it was verified
#   * turntable -> back on frl_apartment_table_01 at (0.41, 0.17), top z=0.758
#   * asset.yaml keeps the 94.29 m^2 floor, which IS the requested reform
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

cp "$WS/tmp/maps.bak" "$REPO/configs/maps.yaml"
echo "  maps.yaml reverted to the original pinned region"

echo
echo "=== state now ==="
echo "  asset.yaml collision (KEPT - this is the requested reform):"
grep -A4 '^collision:' "$REPO/assets/environments/replicad_apartment/asset.yaml" | sed 's/^/    /'
echo "  maps.yaml region (REVERTED):"
grep -A6 'replicad_apartment_floor_pinned' "$REPO/configs/maps.yaml" | sed 's/^/    /'

echo
echo "=== yaml valid? ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
yaml.safe_load(open('$REPO/configs/maps.yaml')); print('  maps.yaml OK')
yaml.safe_load(open('$REPO/assets/environments/replicad_apartment/asset.yaml')); print('  asset.yaml OK')
" 2>&1 | sed 's/^/  /'
