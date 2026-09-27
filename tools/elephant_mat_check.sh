#!/usr/bin/env bash
# ===========================================================================
# Does the elephant actually RENDER WITH ITS TEXTURE?
#
# visual/model.obj says `mtllib visual_geometry.mtl`, but the directory contains
# `model.mtl`, so the reference is broken.  If the texture never loads, the elephant
# renders as flat Blender grey -- and since my still was pixel-identical to the
# delivered clip, the delivered clip would be untextured too.
#
# Decide it by MEASUREMENT: inspect the material actually assigned to the elephant
# mesh in a built scene, and render the same frame twice -- once with the MTL
# reference as shipped, once with it repaired -- and compare.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. how does the renderer add an object asset? ==="
grep -n 'FileBasedObject\|add_asset\|def build_scene\|visual_path\|asset_object' src/physim/render/blender_backend.py | head -25 | sed 's/^/  /'

echo
echo "=== 2. the material on the elephant mesh in a BUILT scene ==="
cat > /tmp/matcheck.py <<'PY'
import sys, os, json, tempfile
sys.path.insert(0, "src")
import bpy
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics import SimulationResult, BodyState
from physim.camera import CameraSpec
from physim.render.blender_backend import PhyCoBlenderBackend

S = "datasets/turntable_spin/seed-005002/x1"
def st(p):
    return tuple(BodyState(frame=int(i["frame"]), time_seconds=float(i["time_seconds"]),
        position=tuple(float(v) for v in i["position"]),
        quaternion=tuple(float(v) for v in i["quaternion"]),
        linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
        angular_velocity=tuple(float(v) for v in i["angular_velocity"]))
        for i in json.load(open(p)))
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_spin_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 4
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get("special_plush_elephant")
smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=v)
cam = CameraSpec(**json.load(open(f"{S}/metadata.json"))["camera"])
one = SimulationResult(trajectory=st(f"{S}/trajectory.json")[:1], collisions=(),
                       support_trajectory=st(f"{S}/support_trajectory.json")[:1])
be = PhyCoBlenderBackend("third_party/phyco-sim",
        tempfile.mkdtemp(prefix="mc_", dir="/data/raw/huzijian/project1_database/tmp"))
be.build_scene(smp, one, asset, ms, cam, cfg)
for o in bpy.data.objects:
    if o.type == "MESH" and "elephant" in o.name:
        print("MC elephant object:", o.name, "verts:", len(o.data.vertices))
        print("MC material slots:", len(o.data.materials))
        for m in o.data.materials:
            if m is None:
                print("MC   slot: None")
                continue
            print(f"MC   slot: {m.name} use_nodes={m.use_nodes}")
            if m.use_nodes:
                for n in m.node_tree.nodes:
                    if n.type == "TEX_IMAGE":
                        print(f"MC     TEX_IMAGE image={n.image.name if n.image else None}")
                    if n.type == "BSDF_PRINCIPLED":
                        bc = n.inputs["Base Color"]
                        print(f"MC     base_color linked={bc.is_linked} default={tuple(round(x,3) for x in bc.default_value)}")
        print("MC uv layers:", [u.name for u in o.data.uv_layers])
# also: which images did Blender actually load?
print("MC images in file:", [i.name for i in bpy.data.images if i.name != "Render Result"][:12])
PY
"$BLENDER" --background --factory-startup --python /tmp/matcheck.py 2>&1 \
  | grep -aE '^MC|Error|Traceback' | sed 's/^/  /'
