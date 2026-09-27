#!/usr/bin/env bash
# ===========================================================================
# DEEP conformance audit of the two assets we intend to share (elephant + apartment)
# against the mentor's published rules (assets/README.md, commit 7a68a71).
#
# Also inspects the .blend INTERNALS (collection names, light names, World name),
# because the mentor requires authored lights in collection `environment_lighting`
# and the authored World as `environment_world` -- and a silent violation of that
# rule has already happened once in this project.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== collision mesh complexity (mentor: <=512 tris default) ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import os
def obj_counts(p):
    v = f = 0
    for line in open(p, errors="ignore"):
        if line.startswith("v "): v += 1
        elif line.startswith("f "): f += 1
    return v, f
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
for name, p in [
    ("elephant collision", f"{R}/assets/objects/gso_sootheze_cold_therapy_elephant/collision/model.obj"),
    ("elephant visual",    f"{R}/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj"),
    ("lime collision (mentor ref)", f"{R}/assets/objects/food_lime/collision/model.obj"),
    ("apartment floor collision", f"{R}/assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.obj"),
]:
    if os.path.isfile(p):
        v, f = obj_counts(p)
        flag = ""
        if "collision" in name and f > 512: flag = "  <-- OVER 512"
        print(f"  {name:30s} verts={v:7d} faces={f:7d}{flag}")
    else:
        print(f"  {name:30s} MISSING")
PY

echo
echo "=== source/ dirs present? (mentor: preserve untouched download) ==="
for a in assets/objects/gso_sootheze_cold_therapy_elephant \
         assets/environments/replicad_apartment \
         assets/objects/food_lime; do
  if [ -d "$a/source" ]; then
    echo "  $a/source EXISTS: $(ls $a/source | head -3 | tr '\n' ' ')"
  else
    echo "  $a/source MISSING"
  fi
done

echo
echo "=== stray files that should NOT ship (.blend1 backups etc.) ==="
find assets/objects/gso_sootheze_cold_therapy_elephant assets/environments/replicad_apartment \
  -type f \( -name '*.blend1' -o -name '*bak*' -o -name '*.tmp' \) -printf '  %10s  %p\n' 2>/dev/null

echo
echo "=== .blend INTERNALS: collections, lights, world ==="
"$BLENDER" --background --factory-startup --python-expr "
import bpy
print('  --- collections ---')
for c in bpy.data.collections: print('    coll:', c.name, 'objs=', len(c.objects))
print('  --- lights ---')
for o in bpy.data.objects:
    if o.type == 'LIGHT':
        c = [x.name for x in o.users_collection]
        print('    light:', o.name, o.data.type, 'colls=', c)
print('  --- world ---')
for w in bpy.data.worlds: print('    world:', w.name)
print('  --- mesh object count ---')
print('    meshes:', len([o for o in bpy.data.objects if o.type=='MESH']))
print('    top-level objects:', [o.name for o in bpy.data.objects if o.parent is None][:12])
" -- "assets/environments/replicad_apartment/visual/scene.blend" 2>&1 | grep -E '^\s+(---|coll:|light:|world:|meshes:|top-level)' | head -30

echo
echo "=== preview scripts available ==="
ls scripts/preview_blender.py scripts/blender_preview_scene.py 2>/dev/null | sed 's/^/  /'
