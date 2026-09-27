#!/usr/bin/env bash
# ===========================================================================
# Inspect the apartment .blend INTERNALS correctly.
#
# My earlier attempt passed the .blend AFTER `--`, so Blender loaded factory
# startup instead and reported the default Cube/Light/Camera -- a false reading.
# The file must come BEFORE --python-expr.
#
# Mentor rule (assets/README.md step 5): the environment must be merged into ONE
# mesh named `environment`, authored lights must remain in collection
# `environment_lighting`, and the authored World must remain as `environment_world`.
# This project has already suffered one SILENT violation of that rule, so verify.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BLEND="$REPO/assets/environments/replicad_apartment/visual/scene.blend"

cat > /tmp/inspect_blend.py <<'PY'
import bpy, sys
print("IB file:", bpy.data.filepath)
print("IB --- collections ---")
for c in bpy.data.collections:
    print(f"IB   coll={c.name!r} objects={len(c.objects)} children={[x.name for x in c.children]}")
print("IB --- objects by type ---")
from collections import Counter
print("IB   ", dict(Counter(o.type for o in bpy.data.objects)))
print("IB --- top-level objects ---")
for o in bpy.data.objects:
    if o.parent is None:
        print(f"IB   top={o.name!r} type={o.type} colls={[x.name for x in o.users_collection]}")
print("IB --- meshes (name, verts, materials) ---")
for m in bpy.data.meshes:
    print(f"IB   mesh={m.name!r} verts={len(m.vertices)} polys={len(m.polygons)} "
          f"mats={[x.name if x else None for x in m.materials]}")
print("IB --- lights ---")
for o in bpy.data.objects:
    if o.type == "LIGHT":
        print(f"IB   light={o.name!r} kind={o.data.type} energy={o.data.energy:.2f} "
              f"colls={[x.name for x in o.users_collection]}")
print("IB --- worlds ---")
for w in bpy.data.worlds:
    print(f"IB   world={w.name!r} use_nodes={w.use_nodes}")
print("IB --- images (packed?) ---")
np = sum(1 for i in bpy.data.images if i.packed_file)
print(f"IB   images={len(bpy.data.images)} packed={np}")
print("IB --- materials count ---", len(bpy.data.materials))
PY

echo "=== .blend internals ==="
"$BLENDER" --background --factory-startup "$BLEND" --python /tmp/inspect_blend.py 2>&1 \
  | grep -aE '^IB' | sed 's/^IB/  /' | head -60

echo
echo "=== does the scene .blend contain the furniture props? ==="
echo "  (mentor: linked collection instances must be realized before merging)"
ls -la "$REPO/assets/environments/replicad_apartment/visual/" | sed 's/^/  /'
