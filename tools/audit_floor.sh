#!/usr/bin/env bash
# 1. fix the samples_per_pixel restore (the first sed missed it)
# 2. Q2: does the ReplicaCAD stage actually contain a usable FLOOR mesh?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== server.yaml around samples_per_pixel ==="
grep -n -B2 -A2 'samples_per_pixel' "$REPO/configs/server.yaml" | cat -A | sed 's/\$$//' | head -12

echo
echo "=== applying fix ==="
sed -i 's/samples_per_pixel: 8/samples_per_pixel: 24/' "$REPO/configs/server.yaml"
grep -n 'samples_per_pixel' "$REPO/configs/server.yaml" | sed 's/^/  /'

echo
echo "=== Q2: identify the FLOOR mesh inside the stage GLB by geometry ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os, struct
import numpy as np
WS = "/data/raw/huzijian/project1_database"
p = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")
with open(p, "rb") as f:
    magic, ver, length = struct.unpack("<III", f.read(12))
    clen, ctype = struct.unpack("<II", f.read(8))
    js = json.loads(f.read(clen).decode("utf-8", "ignore"))
    bin_off = f.tell() + 8
    f.seek(bin_off)
    blob = f.read()

def accessor_bounds(i):
    a = js["accessors"][i]
    return a.get("min"), a.get("max"), a.get("count")

print(f"  meshes: {len(js['meshes'])}, nodes: {len(js['nodes'])}")
rows = []
for mi, m in enumerate(js["meshes"]):
    for pi, prim in enumerate(m["primitives"]):
        pos = prim["attributes"].get("POSITION")
        if pos is None:
            continue
        mn, mx, cnt = accessor_bounds(pos)
        if mn is None:
            continue
        ext = [mx[k] - mn[k] for k in range(3)]
        rows.append((mi, m.get("name", "?"), cnt, mn, mx, ext))

# a floor: very flat in one axis, large in the other two
print()
print("  candidates with a flat axis (potential floor), sorted by area:")
flat = []
for mi, name, cnt, mn, mx, ext in rows:
    order = np.argsort(ext)
    if ext[order[0]] < 0.05 and ext[order[1]] > 1.0 and ext[order[2]] > 1.0:
        area = ext[order[1]] * ext[order[2]]
        flat.append((area, mi, name, cnt, ext, mn, mx, order[0]))
flat.sort(reverse=True)
for area, mi, name, cnt, ext, mn, mx, axis in flat[:8]:
    print(f"    mesh {mi:3d} {name:<12} verts={cnt:6d} extents={np.round(ext,3).tolist()} "
          f"flat_axis={'xyz'[axis]} area={area:.2f} m^2")

if not flat:
    print("    (no flat mesh found -- the stage has no separable floor slab)")
    print()
    print("  largest meshes by volume:")
    rows.sort(key=lambda r: -(r[5][0]*r[5][1]*r[5][2]))
    for mi, name, cnt, mn, mx, ext in rows[:6]:
        print(f"    mesh {mi:3d} {name:<12} verts={cnt:6d} extents={np.round(ext,3).tolist()}")
PY
