#!/usr/bin/env bash
# Just the light-inventory question, isolated: does the imported stage GLB carry
# any light objects of its own?  If it did, adding authored ceiling lights (or our
# own key light) later would double up.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" <<'PY' 2>&1 | grep -E 'LIGHT|^  '
import sys, os, tempfile, json
WS = sys.argv[1]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.renderer import Blender
import bpy

R = os.path.join(WS, "models/backgrounds/replicad")

for name in ("stages/frl_apartment_stage.glb",
             "objects/frl_apartment_sofa.glb",
             "objects/frl_apartment_lamp_01.glb"):
    p = os.path.join(R, name)
    if not os.path.isfile(p):
        print(f"LIGHT {name}: MISSING")
        continue
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    scr = tempfile.mkdtemp(prefix="lt_")
    scene = kb.Scene(resolution=(32, 32), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    Blender(scene, scr, samples_per_pixel=1, use_denoising=False, verbose=True)
    bpy.ops.import_scene.gltf(filepath=p)
    lights = [o.name for o in bpy.data.objects if o.type == "LIGHT"]
    meshes = len([o for o in bpy.data.objects if o.type == "MESH"])
    print(f"LIGHT {name}")
    print(f"  lights={len(lights)} {lights[:6]}")
    print(f"  meshes={meshes}")

# what the scene's own lighting config offers
lc = os.path.join(R, "configs/lighting/frl_apartment_stage.lighting_config.json")
cfg = json.load(open(lc))
kinds = {}
for _k, L in cfg.get("lights", {}).items():
    kinds[L.get("type")] = kinds.get(L.get("type"), 0) + 1
print("LIGHT lighting_config.json")
print(f"  light types: {kinds}")
first = next(iter(cfg.get("lights", {}).values()), {})
print(f"  sample: {json.dumps(first)[:150]}")
PY
