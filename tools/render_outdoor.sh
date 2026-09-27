#!/usr/bin/env bash
# Render each outdoor HDRI as a scene backdrop, with a subject for scale.
#
# Purpose: judge whether these read as real places, or suffer the same "empty and
# unconvincing" problem the bare interiors had before they were furnished.
#
# Setup per environment:
#   * the 4K HDRI drives both the visible background and the ambient light
#   * a large PBR ground plane gives the subject something to stand on and a
#     surface to catch a contact shadow (a panorama alone has no ground)
#   * the GSO elephant sits on the ground as a scale reference
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_outdoor"
rm -rf "$OUT"; mkdir -p "$OUT"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^OUT|^  '
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
ENVS = [
    ("kloppenheim_02",     "street / residential"),
    ("german_town_street", "street / town"),
    ("autumn_park",        "nature / park"),
    ("ballawley_park",     "nature / park 2"),
    ("orlando_stadium",    "sports / stadium"),
]

for tag, label in ENVS:
    scratch = tempfile.mkdtemp(prefix="out_")
    scene = kb.Scene(resolution=(1920, 1080), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=48, use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    # ground: real PBR with correct texel density, so it does not look like paper
    ground = kb.Cube(name="ground", scale=(9.0, 9.0, 0.1), position=(0, 0, -0.1),
                     static=True, segmentation_id=1)
    ground.material = kb.PrincipledBSDFMaterial(color=(0.42, 0.40, 0.36, 1.0),
                                                roughness=0.9)
    scene += ground
    mat, _ = pb.pbr_material(kb, "concrete_floor_worn_001", "concrete_textures",
                             uv_scale=9.0)
    pb.apply_bpy_material(renderer, ground, mat)

    # HDRI: full strength for what the camera sees, modest for the lighting so the
    # contact shadow survives
    p = pb.enable_hdri_file(renderer, tag, strength=0.85, bg_strength=1.0)
    print(f"OUT {tag}: hdri={'ok' if p else 'MISSING'}  [{label}]")

    # key light for a readable shadow
    key = kb.DirectionalLight(name="key", position=(-2.2, -1.6, 3.0), intensity=2.4)
    key.look_at((0, 0, 0.1))
    scene += key

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.0, 0.0, rest), segmentation_id=2)
    scene += obj

    # a wide establishing shot: subject small in a large environment
    cam = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
    cam.position = (1.5, -2.4, 1.35)
    cam.look_at((0.0, 0.0, 0.35))
    scene.camera = cam

    out = renderer.render([0], return_layers=("rgba",))
    img = np.array(out["rgba"], copy=True)[0]
    q = os.path.join(OUT, f"{tag}.png")
    cv2.imwrite(q, img[..., :3][..., ::-1])
    print(f"  wrote {q}")
PY
