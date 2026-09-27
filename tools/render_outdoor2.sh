#!/usr/bin/env bash
# Re-shoot the outdoor environments looking at the HORIZON.
#
# The previous attempt pitched the camera down at the ground plane (look_at z=0.35
# from 1.35 m up), so 90% of the frame was our synthetic floor and the environment
# was reduced to a thin strip.  That is not a fair test of the backdrop.
#
# Here the camera looks nearly level, which is how an outdoor scene is actually
# shot, so the panorama fills the frame.  Two variants per environment:
#   a_wide  - subject small, environment dominant (does the PLACE read as real?)
#   b_close - subject larger, environment as context
#
# The ground plane is shrunk to 12 m so its edge is not visible at this pitch.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor2"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^O2|^  '
import sys, os, json, tempfile
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import bpy, cv2

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
ENVS = [("kloppenheim_02", "street / residential"),
        ("german_town_street", "street / town"),
        ("autumn_park", "nature / park"),
        ("ballawley_park", "nature / park 2"),
        ("orlando_stadium", "sports / stadium")]

VIEWS = [("a_wide", (0.9, -3.4, 1.15), (0.0, 0.0, 0.75), 35.0),
         ("b_close", (0.55, -1.7, 0.95), (0.0, 0.0, 0.22), 40.0)]

for tag, label in ENVS:
    scratch = tempfile.mkdtemp(prefix="o2_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(6.0, 6.0, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(0.40, 0.38, 0.34, 1.0),
                                                roughness=0.92)
    scene += ground
    mat, _ = pb.pbr_material(kb, "concrete_floor_worn_001", "concrete_textures",
                             uv_scale=6.0)
    pb.apply_bpy_material(renderer, ground, mat)

    p = pb.enable_hdri_file(renderer, tag, strength=0.9, bg_strength=1.0)
    key = kb.DirectionalLight(name="key", position=(-2.6, -1.2, 2.6), intensity=2.6)
    key.look_at((0, 0, 0.15))
    scene += key

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest), segmentation_id=2)
    scene += obj

    print(f"O2 {tag}: hdri={'ok' if p else 'MISSING'}  [{label}]")
    for vname, pos, aim, fl in VIEWS:
        cam = kb.PerspectiveCamera(focal_length=fl, sensor_width=36.0)
        cam.position = pos
        cam.look_at(aim)
        scene.camera = cam
        out = renderer.render([0], return_layers=("rgba",))
        img = np.array(out["rgba"], copy=True)[0]
        q = os.path.join(OUT, f"{tag}_{vname}.png")
        cv2.imwrite(q, img[..., :3][..., ::-1])
        print(f"  {vname}: cam=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) -> {os.path.basename(q)}")
PY
