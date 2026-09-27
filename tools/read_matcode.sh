#!/usr/bin/env bash
# ===========================================================================
# Read the NEW material-application code and the segmentation-id assignment.
#
# Two questions:
#  (1) DANGER: turntable.py sets support_material=disc.material.  Can that material
#      ever reach the ACTOR (which would make the plush elephant wood-coloured)?
#      Read the actual code rather than trusting the summary.
#  (2) Why does the segmentation layer contain only labels {0,3} when build_scene
#      assigns environment=1, actor=2, disc=3?  Is the actor unlabelled (a defect),
#      or is my label->object mapping wrong?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== where materials are applied in build_scene ==="
grep -n 'material\|Material' src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== segmentation_id assignments ==="
grep -n 'segmentation_id' src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== the material-application block in context ==="
awk 'NR>=280 && NR<=340' src/physim/render/blender_backend.py | cat -n | sed 's/^/  /'
