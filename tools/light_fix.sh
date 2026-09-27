#!/usr/bin/env bash
# ===========================================================================
# FIX IRON RULE 4 VIOLATION.
#
# FOUND: scene.blend names its light collection `authored_lighting` and its world
# `World`.  The renderer's _append_authored_lighting() looks for
# `environment_lighting` and `environment_world` -- the names the project's own
# normalizer (scripts/prepare_visual_asset.py, LIGHTING_COLLECTION_NAME /
# WORLD_NAME) is supposed to produce.  Because the names did not match, the
# renderer found no authored lights and silently used its hard-coded fallback:
#
#     environment_lighting_source: 'asset_fallback'
#     environment_light_count: 1
#     environment_light_types: ['AREA']
#
# That single AREA light is OUR light, not the scene author's -- exactly what iron
# rule 4 forbids.  The blend was exported straight from ReplicaCAD without running
# the normalizer, so the collection kept its source name.
#
# FIX: rename in the blend to the names the loader expects.  The 7 authored POINT
# lights and the authored World are preserved unchanged -- only their container
# names change, so the render is lit by the scene author's configuration.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BLEND="$REPO/assets/environments/replicad_apartment/visual/scene.blend"

echo "=== 1) stop the render that is using the wrong lighting ==="
tmux kill-session -t t1 2>/dev/null && echo "  t1 stopped" || echo "  t1 not running"

echo
echo "=== 2) back up scene.blend ==="
cp "$BLEND" "$WS/tmp/scene_pre_lightfix.blend"
ls -la "$WS/tmp/scene_pre_lightfix.blend" | sed 's/^/  /'

echo
echo "=== 3) inspect + rename, preserving every light ==="
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background "$BLEND" \
  --python-expr "
import bpy
print('LF BEFORE worlds:', [w.name for w in bpy.data.worlds])
print('LF BEFORE collections:', [c.name for c in bpy.data.collections])
ls=[o for o in bpy.data.objects if o.type=='LIGHT']
print('LF lights found: %d' % len(ls))
for o in sorted(ls, key=lambda x: x.name):
    d=o.data
    print('LF   %-14s %-8s energy=%8.2f color=%s loc=%s' % (
        o.name, d.type, d.energy, tuple(round(v,3) for v in d.color),
        tuple(round(v,3) for v in o.location)))

# --- rename collection ---
c = bpy.data.collections.get('authored_lighting')
if c is not None and bpy.data.collections.get('environment_lighting') is None:
    c.name = 'environment_lighting'
    print('LF renamed collection authored_lighting -> environment_lighting')
else:
    print('LF collection already ok or missing:', [x.name for x in bpy.data.collections])

# --- rename world ---
w = bpy.data.worlds.get('World')
if w is not None and bpy.data.worlds.get('environment_world') is None:
    w.name = 'environment_world'
    print('LF renamed world World -> environment_world')
else:
    print('LF world already ok or missing:', [x.name for x in bpy.data.worlds])

# --- report the world's background so we know the authored ambient ---
for w in bpy.data.worlds:
    if w.use_nodes:
        for n in w.node_tree.nodes:
            if n.type == 'BACKGROUND':
                print('LF world %s background color=%s strength=%s' % (
                    w.name, tuple(round(v,3) for v in n.inputs[0].default_value),
                    round(n.inputs[1].default_value,3)))
    else:
        print('LF world %s (no nodes) color=%s' % (w.name, tuple(round(v,3) for v in w.color)))

print('LF AFTER worlds:', [w.name for w in bpy.data.worlds])
print('LF AFTER collections:', [c.name for c in bpy.data.collections])
bpy.ops.wm.save_mainfile()
print('LF saved')
" 2>&1 | grep -E '^LF'

echo
echo "=== 4) verify the loader now finds authored lighting ==="
cd "$REPO" && "$WS/tools/conda_env/bin/python" - <<'PY'
import bpy, sys
BLEND="/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment/visual/scene.blend"
with bpy.data.libraries.load(BLEND, link=False) as (src, tgt):
    print("  collections available:", src.collections)
    print("  worlds available     :", src.worlds)
    has_c = "environment_lighting" in src.collections
    has_w = "environment_world" in src.worlds
    tgt.collections = ["environment_lighting"] if has_c else []
    tgt.worlds = ["environment_world"] if has_w else []
col = next((c for c in tgt.collections if c), None)
lights = [o for o in col.all_objects if o.type=="LIGHT"] if col else []
print(f"  -> appended collection = {col.name if col else None}")
print(f"  -> authored lights found = {len(lights)}")
for o in lights:
    print(f"     {o.name:14s} {o.data.type:8s} energy={o.data.energy:.2f}")
print(f"  -> authored world = {[w.name for w in tgt.worlds if w]}")
PY
