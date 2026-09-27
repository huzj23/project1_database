#!/usr/bin/env bash
# ===========================================================================
# ROOT CAUSE of both failures.
#
# blender_preview_scene.py and my still harness both use
#     load_simulation_result(trajectory.json, collisions.json)
# which does NOT read support_trajectory.json.  So the turntable's rotation is lost:
#   * the preview fails validation with disc_rotation_degrees = 0.0, and
#   * my still built NO disc at all (support_trajectory empty) -> the "disc" pixels
#     I measured were actually the table/floor, which is why they read neutral 1.03.
#
# Verify by reading load_simulation_result, then re-render the still correctly with
# the support trajectory loaded AND with segmentation, so the disc can be measured
# by its OWN label instead of borrowing the delivered clip's mask.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== load_simulation_result signature + what it reads ==="
grep -n 'def load_simulation_result' -A 30 src/physim/physics/__init__.py | sed 's/^/  /'

echo
echo "=== SimulationResult fields ==="
grep -n 'class SimulationResult' -A 14 src/physim/physics/__init__.py | sed 's/^/  /'
