#!/usr/bin/env bash
# How can we make the ReplicaCAD rooms less "showroom clean"?
#
# Three levers to inspect:
#   1. the authored lighting configs (warmth / mood we are currently ignoring)
#   2. which scene layouts actually carry wall decor (pictures, clocks, mirrors)
#   3. whether the stage's wall/floor materials are addressable so we can
#      re-texture them with Poly Haven PBR
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"

echo "=== 1. authored lighting config (frl_apartment_stage) ==="
f="$R/configs/lighting/frl_apartment_stage.lighting_config.json"
[ -f "$f" ] && head -60 "$f" | sed 's/^/  /'

echo
echo "=== 2. which scene layouts carry wall decor? ==="
"$WS/tools/conda_env/bin/python" - "$R" <<'PY'
import json, os, sys, glob, collections
R = sys.argv[1]
DECOR = ("picture", "clock", "mirror", "poster", "painting", "tv_screen", "monitor")
rows = []
for c in sorted(glob.glob(os.path.join(R, "configs/scenes/*.scene_instance.json"))):
    try:
        cfg = json.load(open(c))
    except Exception:
        continue
    names = [i["template_name"].split("/")[-1] for i in cfg.get("object_instances", [])]
    decor = [n for n in names if any(d in n for d in DECOR)]
    rows.append((os.path.basename(c).replace(".scene_instance.json", ""),
                 len(names), len(decor), ",".join(sorted(set(d.replace("frl_apartment_", "") for d in decor)))))
rows.sort(key=lambda r: (-r[2], -r[1]))
print(f"  {'scene':<34}{'props':>6}{'decor':>7}  decor items")
for name, n, d, items in rows[:16]:
    print(f"  {name:<34}{n:>6}{d:>7}  {items[:60]}")
print(f"  ... total {len(rows)} layouts")
PY

echo
echo "=== 3. stage materials (are walls/floor separable?) ==="
"$WS/tools/conda_env/bin/python" - "$WS" <<'PY'
import sys, os
WS = sys.argv[1]
sys.path.insert(0, os.path.join(WS, "code/vendor/phyco-sim/kubric"))
sys.path.insert(0, os.path.join(WS, "code/vendor/phyco-sim/src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import bpy
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
glb = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")
bpy.ops.import_scene.gltf(filepath=glb)
print(f"  meshes: {len([o for o in bpy.data.objects if o.type=='MESH'])}")
print(f"  materials: {len(bpy.data.materials)}")
for m in bpy.data.materials:
    tex = []
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                tex.append(f"{n.image.name}{tuple(n.image.size)}")
    print(f"    {m.name:<34} images={tex[:2]}")
print("  mesh -> material:")
for o in bpy.data.objects:
    if o.type == "MESH" and o.data.materials:
        mats = [m.name for m in o.data.materials if m]
        print(f"    {o.name:<40} {mats}")
PY
