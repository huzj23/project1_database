#!/usr/bin/env bash
# Two diagnostics for the concept render:
#   A) where is the ReplicaCAD stage's floor in Blender Z?  (probe cubes)
#   B) why is the GSO object untextured?  (inspect the .mtl / .obj)
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

echo "=== B) GSO material wiring ==="
G="$WS/models/gso/Sootheze_Cold_Therapy_Elephant"
echo "  files:"; ls -la "$G" | tail -n +4 | awk '{printf "    %-28s %8d\n", $9, $5}'
echo "  visual_geometry.mtl:"; sed 's/^/    /' "$G/visual_geometry.mtl"
echo "  obj header:"; head -4 "$G/visual_geometry.obj" | sed 's/^/    /'
echo "  obj references mtl?"; grep -c 'mtllib\|usemtl' "$G/visual_geometry.obj" || true

echo
echo "=== A) stage floor probe: cubes at several Z ==="
"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^PROBE|^  '
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

scratch = tempfile.mkdtemp(prefix="probe_")
scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=24, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
pb.build_interior(kb, scene, renderer,
                  pb.InteriorSpec(stage="frl_apartment_stage",
                                  hdri="empty_warehouse_01", hdri_strength=0.6,
                                  fill_intensity=220.0))
print("PROBE backdrop ok")

# five marker cubes along +X at different heights
for i, z in enumerate([2.0, 1.0, 0.5, 0.0, -0.5]):
    c = kb.Cube(name=f"m{i}", scale=(0.05, 0.05, 0.05),
                position=(-1.0 + i * 0.5, 0.0, z),
                static=True, segmentation_id=10 + i)
    c.material = kb.PrincipledBSDFMaterial(color=(1.0, 0.0, 0.0, 1.0))
    scene += c
print("PROBE markers placed at z = 2.0, 1.0, 0.5, 0.0, -0.5")

import bpy
scene.camera = kb.PerspectiveCamera(focal_length=35.0, sensor_width=36.0)
scene.camera.position = (0.0, -4.5, 1.2)
scene.camera.look_at((0.0, 0.0, 0.5))

out = renderer.render([0], return_layers=("rgba",))
img = np.array(out["rgba"], copy=True)[0]
p = os.path.join(WS, "outcomes/_concept", "floor_probe.png")
os.makedirs(os.path.dirname(p), exist_ok=True)
cv2.imwrite(p, img[..., :3][..., ::-1])
print(f"PROBE wrote {p}")
PY
