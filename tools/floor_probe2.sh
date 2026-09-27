#!/usr/bin/env bash
# Find the ReplicaCAD floor height empirically, and check whether the stage
# receives shadows at all.
#
# Method: drop a vertical row of small coloured cubes at 10 cm spacing and one
# tall thin "ruler" wall; the cube whose centre sits flush on the floor reveals
# the floor height visually.  Raycasting is not usable here -- the imported GLB
# geometry is invisible to scene.ray_cast.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_tmp/bin/python"
[ -x "$PY" ] || PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^FLOOR|^  '
import sys, os, tempfile
WS = sys.argv[1]
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
import cv2

COLORS = [(1,0,0), (0,1,0), (0,0,1), (1,1,0), (1,0,1), (0,1,1)]
ZS = [0.0, -0.15, -0.30, -0.45, -0.60, -0.75]

scratch = tempfile.mkdtemp(prefix="floor_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
pb.build_interior(kb, scene, renderer,
                  pb.InteriorSpec(stage="frl_apartment_stage",
                                  hdri="empty_warehouse_01", hdri_strength=0.6,
                                  fill_intensity=220.0))
print("FLOOR backdrop ok")

# marker cubes: 6 cm, spaced 0.35 m apart in x, at 15 cm steps in z
for i, z in enumerate(ZS):
    c = kb.Cube(name=f"m{i}", scale=(0.03, 0.03, 0.03),
                position=(-0.9 + i * 0.36, 0.0, z),
                static=True, segmentation_id=10 + i)
    c.material = kb.PrincipledBSDFMaterial(color=COLORS[i] + (1.0,))
    scene += c
print(f"FLOOR markers z = {ZS}")

import bpy
scene.camera = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
scene.camera.position = (0.0, -3.2, 0.55)
scene.camera.look_at((0.0, 0.0, -0.15))
print(f"FLOOR camera {tuple(round(v,2) for v in scene.camera.position)}")

out = renderer.render([0], return_layers=("rgba",))
img = np.array(out["rgba"], copy=True)[0]
p = os.path.join(WS, "outcomes/_concept", "floor_probe2.png")
os.makedirs(os.path.dirname(p), exist_ok=True)
cv2.imwrite(p, img[..., :3][..., ::-1])
print(f"FLOOR wrote {p}")
PY
