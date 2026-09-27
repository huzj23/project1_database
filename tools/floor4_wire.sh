#!/usr/bin/env bash
# ===========================================================================
# STEP 1c: verify the extracted floor OBJ, then replace the region's box proxy
# with `collision: type: mesh` so the SIMULATOR uses the scene's own floor.
#
# Before: bounds_xy box 1.7 x 1.7 m = 2.89 m^2  (the 垃圾补丁)
# After : the extracted floor mesh, 81.61 m^2
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
ENVDIR="$REPO/assets/environments/replicad_apartment"
MAPS="$REPO/configs/maps.yaml"
cp "$MAPS" "$WS/tmp/maps_pre_floor.bak"

echo "=== verify the extracted OBJ bounds ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np, os
WS="/data/raw/huzijian/project1_database"
p=os.path.join(WS,"code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment/collision/surfaces/replicad_apartment_floor.obj")
V=[];F=0
for ln in open(p):
    if ln.startswith('v '):
        V.append([float(x) for x in ln.split()[1:4]])
    elif ln.startswith('f '):
        F+=1
V=np.array(V)
print(f"  verts={len(V)} faces={F}")
print(f"  x [{V[:,0].min():.3f}, {V[:,0].max():.3f}]  span {V[:,0].max()-V[:,0].min():.3f} m")
print(f"  y [{V[:,1].min():.3f}, {V[:,1].max():.3f}]  span {V[:,1].max()-V[:,1].min():.3f} m")
print(f"  z [{V[:,2].min():.3f}, {V[:,2].max():.3f}]  span {V[:,2].max()-V[:,2].min():.3f} m")
print(f"  -> footprint {V[:,0].max()-V[:,0].min():.2f} x {V[:,1].max()-V[:,1].min():.2f} m")
PY

echo
echo "=== BEFORE (the patch) ==="
sed -n '/replicad_apartment_floor_pinned/,+5p' "$MAPS" | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" - "$MAPS" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
out, in_region, done = [], False, False
for ln in lines:
    if "region_id: replicad_apartment_floor_pinned" in ln:
        in_region = True
        out.append(ln)
        continue
    if in_region and not done:
        s = ln.strip()
        if s.startswith("verification:"):
            ind = ln[:len(ln)-len(ln.lstrip())]
            out.append(ind + "verification: floor_slab_extracted_from_scene_blend_by_geometry")
            continue
        if s.startswith("bounds_xy:"):
            ind = ln[:len(ln)-len(ln.lstrip())]
            # bounds_xy is still required by the loader (sampling bounds); keep it
            # as the clear living-area rectangle, but ADD mesh collision so the
            # SIMULATOR uses the real floor instead of a box proxy.
            out.append(ind + "bounds_xy: [0.1500, 1.8500, -5.1500, -3.4500]")
            out.append(ind + "# The scene's own floor slab replaces the old 2.89 m^2 box proxy.")
            out.append(ind + "# Extracted by geometry from visual/scene.blend: upward faces with")
            out.append(ind + "# z in [0.00, 0.05) -> 202 triangles, 81.61 m^2, footprint")
            out.append(ind + "# x[-2.47, 4.00] y[-6.86, 4.76].  The simulator builds its")
            out.append(ind + "# support body from this mesh instead of from bounds_xy.")
            out.append(ind + "collision:")
            out.append(ind + "  type: mesh")
            out.append(ind + "  mesh: collision/surfaces/replicad_apartment_floor.obj")
            out.append(ind + "  simulation: collision/surfaces/replicad_apartment_floor.urdf")
            out.append(ind + "  triangles: 202")
            out.append(ind + "  max_triangles: 2048")
            out.append(ind + "  mesh_sha256: 3f0399fa53903208f8b2039255dec6339b35cc567bb6e3ad9c05e225849a7699")
            done = True
            in_region = False
            continue
    out.append(ln)
open(p, "w").write("\n".join(out))
print("  maps.yaml region updated:", done)
PY

echo
echo "=== AFTER ==="
sed -n '/replicad_apartment_floor_pinned/,+14p' "$MAPS" | sed 's/^/  /'

echo
echo "=== loader check: does the mesh collision resolve? ==="
cd "$REPO" && "$WS/tools/conda_env/bin/python" - <<'PY'
import sys; sys.path.insert(0,"src")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
m=mm.get("replicad_apartment", require_files=True)
for s in m.surfaces:
    print(f"  surface {s.surface_id}")
    print(f"    collision_simulation_path = {s.collision_simulation_path}")
    print(f"    exists                    = {s.collision_simulation_path.is_file() if s.collision_simulation_path else None}")
    print(f"    ==> simulator will use    = {'MESH (scene own floor)' if s.collision_simulation_path else 'BOX from bounds_xy'}")
PY
