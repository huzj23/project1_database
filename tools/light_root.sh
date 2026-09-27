#!/usr/bin/env bash
# ===========================================================================
# IRON RULE 4 ROOT CAUSE.
#
# scene.blend contains a collection named `authored_lighting` holding 7 POINT
# lights.  The renderer's _append_authored_lighting() looks for a collection named
# `environment_lighting` and a world named `environment_world`.  The names do not
# match, so authored_lights == [] and the renderer silently falls back to a single
# hard-coded AREA light -- our own light, which iron rule 4 forbids.
#
# Establish:
#   1. is there a normalization script that produces `environment_lighting`?
#   2. what does the environment asset.yaml `render` block say?
#   3. does scene.blend have a world named environment_world?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== who produces 'environment_lighting' / 'environment_world'? ==="
grep -rn 'environment_lighting\|environment_world\|authored_lighting' \
  --include='*.py' --include='*.yaml' --include='*.md' . 2>/dev/null | sed 's/^/  /'

echo
echo "=== the environment asset.yaml render + visual blocks ==="
sed -n '/^render:/,/^[a-z]/p' assets/environments/replicad_apartment/asset.yaml | sed 's/^/  /'
echo "  ---"
sed -n '/^visual:/,/^collision:/p' assets/environments/replicad_apartment/asset.yaml | sed 's/^/  /'

echo
echo "=== worlds inside scene.blend ==="
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" \
  --python-expr "
import bpy
print('LW worlds:', [w.name for w in bpy.data.worlds])
print('LW collections:', [c.name for c in bpy.data.collections])
for c in bpy.data.collections:
    print('LW   %s: objects=%s' % (c.name, [o.name for o in c.objects]))
" 2>&1 | grep -E '^LW'
