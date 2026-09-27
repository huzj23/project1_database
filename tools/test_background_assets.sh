#!/usr/bin/env bash
# Feasibility test: can our Blender 3.4.1 / bpy pipeline render
#   (a) a ReplicaCAD GLB stage as a static, render-only background, and
#   (b) a GSO object as a physics-ready FileBasedObject,
# and can we reproduce the colleague's studio look (softbox rig + cyclorama)?
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -X faulthandler - <<'PY' 2>&1 | grep -vE '^Fra:|^Saved:|^ ?Time:|^ *$'
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
print('TEST numpy aliases patched:', pc.patch_numpy_legacy_aliases(), flush=True)
from kubric.simulator import PyBullet
from kubric.renderer import Blender

def s(*a): print("TEST", *a, flush=True)

WS = "/data/raw/huzijian/project1_database"
scratch = tempfile.mkdtemp(prefix="fprobe_")
scene = kb.Scene(resolution=(640, 360), frame_start=0, frame_end=2,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=16, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
s("views ok")

# ---- (a) ReplicaCAD GLB as render-only static background -------------------
glb = os.path.join(WS, "models/backgrounds/replicad/Baked_sc0_staging_00.glb")
bg = kb.FileBasedObject(
    name="replicad_stage",
    simulation_filename=None,          # <- pybullet ignores it (render-only)
    render_filename=glb,
    static=True,
    background=True,
    segmentation_id=1,
)
s("bg object constructed, simulation_filename =", bg.simulation_filename)
scene += bg
s("bg added to scene")

# ---- (b) GSO object as a normal physics-ready body -------------------------
gdir = os.path.join(WS, "models/gso_probe")
import json
d = json.load(open(os.path.join(gdir, "data.json")))
k = d["kwargs"]
gso = kb.FileBasedObject(
    name=d["id"],
    simulation_filename=os.path.join(gdir, "object.urdf"),
    render_filename=os.path.join(gdir, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in k["bounds"]),
    mass=k["mass"],
    scale=6.0,
    position=(0.0, 0.0, 1.0),
    segmentation_id=2,
)
scene += gso
s("gso added:", d["id"], "category", d["metadata"]["category"], "mass", k["mass"])

# ---- (c) colleague-style studio rig: cyclorama + 3-point softbox ----------
# floor + back wall forming a cyclorama
floor = kb.Cube(name="floor", scale=(6, 6, 0.1), position=(0, 0, -0.1),
                static=True, segmentation_id=3)
floor.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0),
                                           roughness=0.85, metallic=0.0)
scene += floor
wall = kb.Cube(name="back_wall", scale=(6, 0.1, 4), position=(0, 5.0, 4.0),
               static=True, segmentation_id=4)
wall.material = kb.PrincipledBSDFMaterial(color=(0.6, 0.6, 0.6, 1.0),
                                          roughness=0.9, metallic=0.0)
scene += wall
s("cyclorama ok")

# three-point rig: large softbox key + front fill + cool rim
key = kb.RectAreaLight(name="Large Softbox", position=(3.0, -3.0, 5.0),
                       intensity=900.0, width=4.0, height=4.0)
key.look_at((0, 0, 1.0))
scene += key
fill = kb.RectAreaLight(name="Front Fill", position=(-3.5, -4.0, 2.5),
                        intensity=250.0, width=3.0, height=3.0)
fill.look_at((0, 0, 1.0))
scene += fill
rim = kb.RectAreaLight(name="Cool Wall Rim", position=(-1.0, 4.0, 4.0),
                       intensity=400.0, width=2.0, height=2.0)
rim.look_at((0, 0, 1.0))
scene += rim
s("3-point rig ok")

# HDRI ambient (we already cache empty_warehouse_01 -- same as the colleague)
try:
    pc.enable_hdri(renderer, "empty_warehouse_01")
    s("HDRI empty_warehouse_01 enabled")
except Exception as e:
    s("HDRI failed:", e)

# ---- camera + motion blur --------------------------------------------------
scene.camera = kb.PerspectiveCamera(focal_length=55.0, sensor_width=36.0)
scene.camera.position = (2.5, -20.0, 8.5)
scene.camera.look_at((0, 0, 1.0))
s("camera ok")

import bpy
bpy.context.scene.render.motion_blur_shutter = 0.25
bpy.context.scene.render.use_motion_blur = True
s("motion blur shutter", bpy.context.scene.render.motion_blur_shutter,
  "use_motion_blur", bpy.context.scene.render.use_motion_blur)

out = renderer.render(list(range(3)), return_layers=("rgba", "segmentation", "depth"))
s("RENDER OK", {k2: v.shape for k2, v in out.items()})
seg = np.array(out["segmentation"], copy=True)
s("segmentation unique:", np.unique(seg).tolist())
rgba = np.array(out["rgba"], copy=True)
s("rgba mean:", float(rgba[..., :3].mean()))
s("ALL TESTS PASSED")
PY
