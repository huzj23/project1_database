#!/usr/bin/env bash
# Decisive shadow test: a big cube floating over the floor with a strong sun.
# If that casts no shadow, shadows are disabled somewhere in the pipeline rather
# than merely being too soft.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_shadowtest"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^SH|^  '
import sys, os, tempfile
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
import cv2, bpy
os.makedirs(OUT, exist_ok=True)

def run(tag, ambient, sun, use_shadow_flag):
    scratch = tempfile.mkdtemp(prefix="sh_")
    scene = kb.Scene(resolution=(640, 360), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    fl = kb.Cube(name="floor", scale=(4, 4, 0.1), position=(0, 0, -0.1),
                 static=True, segmentation_id=1)
    fl.material = kb.PrincipledBSDFMaterial(color=(0.6, 0.6, 0.6, 1.0), roughness=0.9)
    scene += fl

    blk = kb.Cube(name="block", scale=(0.25, 0.25, 0.25),
                  position=(0, 0, 0.75), static=True, segmentation_id=2)
    blk.material = kb.PrincipledBSDFMaterial(color=(0.8, 0.3, 0.3, 1.0))
    scene += blk

    if ambient > 0:
        pc.enable_hdri(renderer, "empty_warehouse_01")
        renderer._set_ambient_light_hdri(
            os.path.join(WS, "models/hdri_haven/empty_warehouse_01.tar.gz"), strength=ambient)
    else:
        renderer._set_ambient_light_color((0.05, 0.05, 0.05, 1.0))
        renderer._set_background_color((0.2, 0.3, 0.45, 1.0))

    sun_l = kb.DirectionalLight(name="Sun", position=(2.5, -3.0, 4.0), intensity=sun,
                                color=(1.0, 0.98, 0.95))
    sun_l.look_at((0, 0, 0.5))
    scene += sun_l

    # can we even set the flag?
    try:
        bo = sun_l.linked_objects.get(renderer)
        before = getattr(bo.data, "use_shadow", None)
        if bo is not None and hasattr(bo.data, "use_shadow"):
            bo.data.use_shadow = use_shadow_flag
        print(f"SH [{tag}] sun use_shadow {before} -> {getattr(bo.data,'use_shadow',None)}")
    except Exception as e:
        print(f"SH [{tag}] could not touch use_shadow: {e}")

    scene.camera = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
    scene.camera.position = (1.8, -2.6, 1.6)
    scene.camera.look_at((0, 0, 0.35))

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    p = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(p, img[..., :3][..., ::-1])
    # crude shadow probe: darkest pixel in the lower half (the floor area)
    lower = img[img.shape[0]//2:, :, :3].astype(float).mean(axis=2)
    print(f"  floor min/mean luminance = {lower.min():.0f} / {lower.mean():.0f}")
    print(f"  wrote {p}")

run("noamb_sun", 0.0, 5.0, True)
run("amb0p25_sun", 0.25, 5.0, True)
run("amb0p25_sun_noshadow", 0.25, 5.0, False)
PY
