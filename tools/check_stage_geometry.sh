#!/usr/bin/env bash
# DECISIVE TEST: is the ReplicaCAD stage geometry actually rendering, or have we
# been looking at the HDRI panorama all along?
#
# Method: build the interior with NO HDRI, set a distinctive flat background
# colour, and report where the imported geometry actually sits.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^CHK|^  '
import sys, os, tempfile
WS = sys.argv[1]
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

SDIR = os.path.join(WS, "models/backgrounds/replicad/stages")
OUT = os.path.join(WS, "outcomes/_concept")
os.makedirs(OUT, exist_ok=True)
W, H = 960, 540

for stage in ("frl_apartment_stage", "Stage_v3_sc0_staging"):
    scratch = tempfile.mkdtemp(prefix="chk_")
    scene = kb.Scene(resolution=(W, H), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=8, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    glb = os.path.join(SDIR, f"{stage}.glb")
    obj = kb.FileBasedObject(name="stage", simulation_filename=None,
                             render_filename=glb, static=True,
                             background=True, segmentation_id=1)
    scene += obj
    print(f"CHK stage={stage}")

    # where did the imported meshes actually land?
    dg = bpy.context.evaluated_depsgraph_get()
    n_mesh = 0
    lo = np.array([1e18] * 3); hi = np.array([-1e18] * 3)
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        n_mesh += 1
        me = o.evaluated_get(dg).to_mesh()
        if len(me.vertices):
            co = np.array([v.co[:] for v in me.vertices])
            mw = np.array(o.matrix_world)
            w = co @ mw[:3, :3].T + mw[:3, 3]
            lo = np.minimum(lo, w.min(axis=0)); hi = np.maximum(hi, w.max(axis=0))
        o.evaluated_get(dg).to_mesh_clear()
    print(f"  meshes imported: {n_mesh}")
    if n_mesh:
        print(f"  geom bounds  min={np.round(lo,2).tolist()}  max={np.round(hi,2).tolist()}")
        print(f"  centre       {np.round((lo+hi)/2,2).tolist()}")

    # flat background so any real geometry is unmistakable
    renderer._set_background_color((0.0, 0.8, 0.0, 1.0))
    renderer._set_ambient_light_color((0.6, 0.6, 0.6, 1.0))
    scene += kb.DirectionalLight(name="key", position=(3, -4, 6), intensity=3.0)

    # aim at the geometry centre if we found one, else at the origin
    centre = ((lo + hi) / 2) if n_mesh else np.zeros(3)
    span = float(np.max(hi - lo)) if n_mesh else 6.0
    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = tuple(centre + np.array([0.0, -max(span, 3.0) * 1.2, max(span, 3.0) * 0.35]))
    cam.look_at(tuple(centre))
    scene.camera = cam
    print(f"  camera at {tuple(round(v,1) for v in cam.position)} looking at "
          f"{tuple(round(v,1) for v in centre)}")

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    # how much of the frame is NOT the green background?
    rgb = img[..., :3].astype(int)
    green = (rgb[..., 1] > 180) & (rgb[..., 0] < 80) & (rgb[..., 2] < 80)
    cov = 100.0 * (1.0 - green.mean())
    p = os.path.join(OUT, f"chk_{stage}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    print(f"  background(green) coverage {100-green.mean()*100:.1f}%  "
          f"-> non-background {cov:.1f}%")
    print(f"  wrote {p}")

    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
    print()
PY
