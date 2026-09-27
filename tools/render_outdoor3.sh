#!/usr/bin/env bash
# Outdoor backdrops with GROUND MATERIALS THAT MATCH THE ENVIRONMENT.
#
# Previously every environment sat on the same concrete floor, which made the
# backdrop read as fake -- a park paved in concrete, a stadium paved in concrete.
# The panorama has no ground of its own (it stops at the horizon), so the floor we
# add is the only ground the viewer ever sees and it has to belong to the place.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor3"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^O3|^  '
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

# (hdri, label, ground asset, ground category, uv scale, tint)
ENVS = [
    ("kloppenheim_02",     "street / residential", "grass_ground",     "grass_textures",   3.0, (0.90, 0.92, 0.85)),
    ("german_town_street", "street / town",        "asphalt_01",       "asphalt_textures", 2.5, (1.00, 1.00, 1.00)),
    ("autumn_park",        "nature / park",        "grass_ground",     "grass_textures",   3.0, (0.95, 0.95, 0.85)),
    ("ballawley_park",     "nature / park 2",      "grass_ground",     "grass_textures",   3.5, (0.88, 0.92, 0.82)),
    ("orlando_stadium",    "sports / stadium",     "running_track",    "sport_textures",   2.0, (1.00, 1.00, 1.00)),
]

VIEWS = [("a_wide", (0.9, -3.4, 1.15), (0.0, 0.0, 0.72), 35.0),
         ("b_close", (0.55, -1.7, 0.95), (0.0, 0.0, 0.22), 40.0)]

for tag, label, asset, cat, uvs, tint in ENVS:
    scratch = tempfile.mkdtemp(prefix="o3_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    ground = kb.Cube(name="ground", scale=(7.0, 7.0, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(*tint, 1.0), roughness=0.92)
    scene += ground
    # tint the diffuse through the Principled base colour multiplier
    mat, info = pb.pbr_material(kb, asset, cat, uv_scale=uvs)
    if pb.apply_bpy_material(renderer, ground, mat):
        print(f"O3 {tag}: ground={asset} ({cat}) uv={uvs}  [{label}]")
    else:
        print(f"O3 {tag}: GROUND MATERIAL FAILED -> {asset}")

    pb.enable_hdri_file(renderer, tag, strength=0.9, bg_strength=1.0)
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

    for vname, pos, aim, fl in VIEWS:
        cam = kb.PerspectiveCamera(focal_length=fl, sensor_width=36.0)
        cam.position = pos
        cam.look_at(aim)
        scene.camera = cam
        out = renderer.render([0], return_layers=("rgba",))
        img = np.array(out["rgba"], copy=True)[0]
        q = os.path.join(OUT, f"{tag}_{vname}.png")
        cv2.imwrite(q, img[..., :3][..., ::-1])
    print(f"  wrote {tag}_a_wide / _b_close")
PY
