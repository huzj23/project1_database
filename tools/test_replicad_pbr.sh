#!/usr/bin/env bash
# Does the NON-baked ReplicaCAD stage (standard PBR) render correctly?
# The baked variant stores lightmaps in a 2nd UV set with a custom shader, which
# plain glTF import does not reproduce.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - <<'PY' 2>&1 | grep -vE '^Fra:|^Saved:|^ ?Time:|^ *$'
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import cv2, bpy

WS = "/data/raw/huzijian/project1_database"
OUT = os.path.join(WS, "outcomes/_look_probe")
os.makedirs(OUT, exist_ok=True)

def probe(glb, tag, cam_pos, cam_look):
    scratch = tempfile.mkdtemp(prefix="rglb_")
    scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=24, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    bg = kb.FileBasedObject(name="stage", simulation_filename=None,
                            render_filename=glb, static=True, background=True,
                            segmentation_id=1)
    scene += bg

    # report scene bounds so we can place the camera sensibly
    import mathutils
    xs, ys, zs = [], [], []
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    if xs:
        print(f"BOUNDS {tag}: x[{min(xs):.1f},{max(xs):.1f}] "
              f"y[{min(ys):.1f},{max(ys):.1f}] z[{min(zs):.1f},{max(zs):.1f}]", flush=True)
    ntex = len([i for i in bpy.data.images if i.size[0] > 0])
    print(f"IMAGES {tag}: {ntex} textures loaded", flush=True)

    pc.enable_hdri(renderer, "empty_warehouse_01")
    scene.camera = kb.PerspectiveCamera(focal_length=24.0, sensor_width=36.0)
    scene.camera.position = cam_pos
    scene.camera.look_at(cam_look)
    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"glb_{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print("WROTE", p, "mean", float(img[..., :3].mean()), flush=True)

probe(os.path.join(WS, "models/backgrounds/replicad/frl_apartment_stage.glb"),
      "interactive", (0.0, -6.0, 2.0), (0.0, 0.0, 1.5))
print("DONE", flush=True)
PY
