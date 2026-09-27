#!/usr/bin/env bash
# ===========================================================================
# IRON RULE 4: are the scene author's lights actually being used?
#
# The rolling render reported environment_lighting_source = 'asset_fallback' with
# a single AREA light, meaning _append_authored_lighting() found NO lights in
# map_spec.visual_path.  If so the image is lit by a hard-coded fallback, which is
# exactly what iron rule 4 forbids.
#
# Two things to establish:
#   1. what does _append_authored_lighting() look for?
#   2. what lights actually exist in scene.blend, and what is map_spec.visual_path?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== _append_authored_lighting (lines 385-425) ==="
sed -n '385,425p' src/physim/render/blender_backend.py | sed 's/^/  /'

echo
echo "=== what is map_spec.visual_path for replicad_apartment? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys; sys.path.insert(0,"src")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
m=mm.get("replicad_apartment", require_files=True)
print("  visual_path =", m.visual_path)
print("  exists      =", m.visual_path.exists() if m.visual_path else None)
print("  lighting    =", getattr(m, "lighting", None))
print("  map_id      =", m.map_id)
for a in ("visual_path","lighting_config","lighting_path","metadata"):
    print(f"  {a}:", getattr(m, a, "<none>") if a!="metadata" else list(getattr(m,'metadata',{}).keys()))
PY

echo
echo "=== lights actually inside scene.blend ==="
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" \
  --python-expr "
import bpy
print('LT total objects:', len(bpy.data.objects))
print('LT collections:', [c.name for c in bpy.data.collections])
print('LT scenes:', [s.name for s in bpy.data.scenes])
for s in bpy.data.scenes:
    print('LT scene %s: world=%s' % (s.name, s.world.name if s.world else None))
    ls=[o for o in s.objects if o.type=='LIGHT']
    print('LT   lights in scene:', len(ls))
    for o in ls:
        print('LT     %-28s type=%-10s energy=%.2f loc=%s coll=%s' % (
            o.name, o.data.type, o.data.energy,
            tuple(round(v,3) for v in o.location),
            [c.name for c in o.users_collection]))
print('LT all light datablocks:', [o.name for o in bpy.data.objects if o.type=='LIGHT'])
print('LT all collections w/ lights:')
for c in bpy.data.collections:
    ls=[o.name for o in c.objects if o.type=='LIGHT']
    if ls: print('LT   %s -> %s' % (c.name, ls))
" 2>&1 | grep -E '^LT'
