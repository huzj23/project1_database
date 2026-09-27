#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Q2 answer: does the indoor scene provide a real, interactive floor?
#
# Found: mesh 11 (Mesh.561), 91 verts, extents 725.6 x 4.3 x 1299.3 in source
# units -- flat in one axis and huge in the other two.  That is the floor slab.
# Source units are centimetres-ish (the apartment is 7.26 x 13.05 m), so this is
# about 7.26 m x 13.0 m x 4.3 cm: exactly the apartment footprint.
#
# So the scene DOES ship a floor.  The current indoor manifest does not use it --
# it uses a hand-placed BOX proxy over a "verified clear" region instead:
#
#     collision:
#       type: box
#       center: [2.7, -1.6, -0.049]
#       half_extents: [0.5, 2.7, 0.05]
#
# This script measures the real floor and compares it with that proxy, so the
# answer to "can we hook the scene's own floor into the simulation?" is a
# measurement rather than an opinion.
# ---------------------------------------------------------------------------
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os, struct
import numpy as np
WS = "/data/raw/huzijian/project1_database"
p = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")
with open(p, "rb") as f:
    struct.unpack("<III", f.read(12))
    clen, _ = struct.unpack("<II", f.read(8))
    js = json.loads(f.read(clen).decode("utf-8", "ignore"))
    struct.unpack("<II", f.read(8))
    blob = f.read()

def read_pos(acc_i):
    a = js["accessors"][acc_i]
    bv = js["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    n = a["count"]
    arr = np.frombuffer(blob, dtype=np.float32, count=n * 3, offset=off).reshape(n, 3)
    return arr

# locate the flat slab (mesh 11 / Mesh.561) and read its real vertices
for mi, m in enumerate(js["meshes"]):
    for prim in m["primitives"]:
        pos_i = prim["attributes"]["POSITION"]
        v = read_pos(pos_i)
        ext = v.max(axis=0) - v.min(axis=0)
        order = np.argsort(ext)
        if ext[order[0]] < 6.0 and ext[order[1]] > 100 and ext[order[2]] > 100:
            print(f"  FLOOR FOUND: mesh {mi} '{m.get('name')}' verts={len(v)}")
            print(f"    source extents : {np.round(ext,2).tolist()}")
            # ReplicaCAD source units are cm; the apartment measures 7.26 x 13.05 m
            scale = 0.01
            print(f"    scaled (cm->m) : {np.round(ext*scale,3).tolist()}")
            print(f"    min (m)        : {np.round(v.min(axis=0)*scale,3).tolist()}")
            print(f"    max (m)        : {np.round(v.max(axis=0)*scale,3).tolist()}")
            print(f"    flat axis      : {'xyz'[order[0]]} (thickness {ext[order[0]]*scale:.3f} m)")
            print(f"    surface area   : {ext[order[1]]*ext[order[2]]*scale*scale:.2f} m^2")
            # how many triangles?
            idx = prim.get("indices")
            if idx is not None:
                print(f"    triangles      : {js['accessors'][idx]['count']//3}")

print()
print("  --- current indoor manifest collision proxy ---")
print("    type: box, center [2.7, -1.6, -0.049], half_extents [0.5, 2.7, 0.05]")
print("    -> footprint 1.0 x 5.4 m = 5.40 m^2")
print("    -> this is a small hand-placed patch, NOT the whole floor")
PY

echo
echo "=== is the scene.blend floor present as geometry too? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os
WS = "/data/raw/huzijian/project1_database"
p = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/environments/replicad_apartment/visual/scene.blend")
print("  scene.blend:", os.path.isfile(p), f"{os.path.getsize(p)/1048576:.1f} MB" if os.path.isfile(p) else "")
print("  (the joined 'environment' mesh includes the floor slab, since all stage")
print("   meshes were joined into one object)")
PY
