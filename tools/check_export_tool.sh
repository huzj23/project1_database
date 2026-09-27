#!/usr/bin/env bash
# Is export_blend_joined.sh parameterized, and can we get a SECOND scene?
# We only have ONE exported scene (replicad_apartment).  The 4 Stage GLBs are on
# disk with their own lighting configs, so exporting one more would give the plan
# real scene variety instead of 7 videos in the same apartment.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== export_blend_joined.sh: is the stage hardcoded? ==="
grep -n 'STAGE\|stages\|apt_0\|scene_instance\|STAGE_NAME\|for ' \
    "$WS/tools/export_blend_joined.sh" 2>/dev/null | head -25 | sed 's/^/  /'

echo
echo "=== its tail (what it writes) ==="
tail -25 "$WS/tools/export_blend_joined.sh" 2>/dev/null | sed 's/^/  /'

echo
echo "=== apt_1..5 layouts exist? ==="
ls -1 "$WS/models/backgrounds/replicad/configs/scenes"/apt_*.json 2>/dev/null | sed 's/^/  /'

echo
echo "=== lighting configs available (one per scene) ==="
ls -1 "$WS/models/backgrounds/replicad/configs/lighting"/*.json 2>/dev/null | sed 's/^/  /'
