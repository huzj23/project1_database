#!/usr/bin/env bash
# Render a visual proof of the proposed "improved" look:
#   ReplicaCAD GLB background + GSO prop + cyclorama + 3-point softbox rig
#   + HDRI ambient + motion blur, at the colleague's 1280x720 / 55mm framing.
# Saves a PNG so it can be inspected locally.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - <<'PY' 2>&1 | grep -vE '^Fra:|^Saved:|^ ?Time:|^ *$'
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import cv2

WS = "/data/raw/huzijian/project1_database"
OUT = os.path.join(WS, "outcomes/_look_probe")
os.makedirs(OUT, exist_ok=True)

def build(variant):
    scratch = tempfile.mkdtemp(prefix="look_")
    scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=1,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    if variant == "replicad":
        # ReplicaCAD baked stage used purely as a visual background (no physics)
        bg = kb.FileBasedObject(
            name="stage", simulation_filename=None,
            render_filename=os.path.join(WS, "models/backgrounds/replicad/Baked_sc0_staging_00.glb"),
            static=True, background=True, segmentation_id=1)
        scene += bg
    else:
        # colleague-style cyclorama: floor + back wall
        fl = kb.Cube(name="floor", scale=(8, 8, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
        fl.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0), roughness=0.85)
        scene += fl
        wl = kb.Cube(name="back_wall", scale=(8, 0.1, 5), position=(0, 5.5, 5.0),
                     static=True, segmentation_id=3)
        wl.material = kb.PrincipledBSDFMaterial(color=(0.62, 0.62, 0.62, 1.0), roughness=0.9)
        scene += wl

    # GSO prop
    gdir = os.path.join(WS, "models/gso_probe")
    d = json.load(open(os.path.join(gdir, "data.json")))
    k = d["kwargs"]
    obj = kb.FileBasedObject(
        name=d["id"], simulation_filename=os.path.join(gdir, "object.urdf"),
        render_filename=os.path.join(gdir, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in k["bounds"]), mass=k["mass"],
        scale=8.0, position=(0.0, 0.0, 1.2), segmentation_id=2)
    scene += obj

    # studio 3-point rig (softboxes), like the colleague's scene graph
    for nm, pos, inten, size in (
        ("Large Softbox", (3.5, -4.0, 5.5), 1400.0, 5.0),
        ("Front Fill",    (-4.5, -5.0, 2.5),  350.0, 4.0),
        ("Cool Wall Rim", (-1.0, 5.0, 4.5),   600.0, 3.0)):
        lt = kb.RectAreaLight(name=nm, position=pos, intensity=inten,
                              width=size, height=size)
        lt.look_at((0, 0, 1.2))
        scene += lt

    pc.enable_hdri(renderer, "empty_warehouse_01")

    scene.camera = kb.PerspectiveCamera(focal_length=55.0, sensor_width=36.0)
    scene.camera.position = (3.0, -9.0, 4.0)
    scene.camera.look_at((0, 0, 1.2))

    import bpy
    bpy.context.scene.render.use_motion_blur = True
    bpy.context.scene.render.motion_blur_shutter = 0.25
    return scene, renderer

for variant in ("cyclorama", "replicad"):
    scene, renderer = build(variant)
    out = renderer.render([0, 1], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"look_{variant}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print("WROTE", p, img.shape, flush=True)
print("DONE", flush=True)
PY
