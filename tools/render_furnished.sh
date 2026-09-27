#!/usr/bin/env bash
# Render a FURNISHED ReplicaCAD apartment.
#
# The empty look in our D batch is because we only loaded the stage (architecture).
# The same download ships 91 authored scene instances that place ~95 everyday
# props (sofa, table, rug, books, plants, lamp, TV...) at exact transforms, plus
# a lighting config.  This loads one and renders it, to judge whether the scene
# reads as "everyday" once furnished.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_scene_survey"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^SC|^  '
import sys, os, json, tempfile, math
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2

R = os.path.join(WS, "models/backgrounds/replicad")
STAGE = os.path.join(R, "stages/frl_apartment_stage.glb")
SCENE_JSON = os.path.join(R, "configs/scenes/apt_0.scene_instance.json")

def render_one(tag, furnish, cam_pos, look_at, res=(960, 540), spp=24):
    scratch = tempfile.mkdtemp(prefix="sc_")
    scene = kb.Scene(resolution=res, frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=spp,
                       use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    # stage (direct import -- Kubric's glTF path mangles the transforms)
    bpy.ops.import_scene.gltf(filepath=STAGE)
    n0 = len([o for o in bpy.data.objects if o.type == "MESH"])

    placed, failed = 0, 0
    if furnish:
        cfg = json.load(open(SCENE_JSON))
        for inst in cfg.get("object_instances", []):
            tpl = inst["template_name"].split("/")[-1]
            glb = os.path.join(R, "objects", f"{tpl}.glb")
            if not os.path.isfile(glb):
                failed += 1
                continue
            before = {o.name for o in bpy.data.objects}
            try:
                bpy.ops.import_scene.gltf(filepath=glb)
            except Exception:
                failed += 1
                continue
            new = [o for o in bpy.data.objects if o.name not in before]
            tr = inst.get("translation", [0, 0, 0])
            qt = inst.get("rotation", [0, 0, 0, 1])   # habitat: [x,y,z,w]
            for o in new:
                # habitat is Y-up; our stage import already converted to Z-up,
                # so apply the same convention here: (x, y, z)_hab -> (x, -z, y)
                o.location = (float(tr[0]) + o.location.x,
                              float(-tr[2]) + o.location.y,
                              float(tr[1]) + o.location.z)
            placed += 1
    n1 = len([o for o in bpy.data.objects if o.type == "MESH"])
    print(f"SC {tag}: stage meshes={n0}  props placed={placed} failed={failed}  total meshes={n1}")

    renderer._set_ambient_light_color((0.55, 0.55, 0.58, 1.0))
    renderer._set_background_color((0.30, 0.34, 0.40, 1.0))
    sun = kb.DirectionalLight(name="sun", position=(3, -4, 6), intensity=2.2)
    sun.look_at((0, 0, 0.8)); scene += sun
    fill = kb.RectAreaLight(name="fill", position=(-2.5, -2.5, 2.6),
                            intensity=260.0, width=4.0, height=3.0)
    fill.look_at((0, 0, 0.8)); scene += fill

    cam = kb.PerspectiveCamera(focal_length=28.0, sensor_width=36.0)
    cam.position = cam_pos
    cam.look_at(look_at)
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  wrote {p}")

# 1) empty stage, same wide view
render_one("01_stage_empty", False, (5.5, -7.5, 3.2), (0.5, -1.0, 0.8))
# 2) furnished with apt_0 props
render_one("02_apartment_furnished", True, (5.5, -7.5, 3.2), (0.5, -1.0, 0.8))
PY
