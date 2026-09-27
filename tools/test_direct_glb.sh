#!/usr/bin/env bash
# DECISIVE: import the ReplicaCAD GLB directly with bpy (no Kubric asset path)
# and see whether the room lands at a sane size/orientation.
#
# Kubric's glTF branch force-sets `rotation_quaternion = (0.707,-0.707,0,0)` on
# the joined object and applies rotation only.  Each ReplicaCAD node already
# carries its own +90deg-X rotation and a 0.01 scale (source data is in cm), so
# that overwrite is the prime suspect for the 1300 m bounding box.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_replicad_fix"

"$PY" -u - "$WS" "$OUT" <<'PY' 2>&1 | grep -E '^DIR|^  '
import sys, os, tempfile
WS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.renderer import Blender
import bpy, cv2
os.makedirs(OUT, exist_ok=True)

GLB = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")

# a scene + renderer so we get a camera/lights pipeline, but we add the stage
# ourselves rather than through scene += FileBasedObject
scene = kb.Scene(resolution=(960, 540), frame_start=0, frame_end=0,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, tempfile.mkdtemp(prefix="dir_"),
                   samples_per_pixel=16, use_denoising=True, verbose=True)
print("DIR renderer ready")

# --- direct import ---------------------------------------------------------
before = {o.name for o in bpy.data.objects}
bpy.ops.import_scene.gltf(filepath=GLB)
added = [o for o in bpy.data.objects if o.name not in before]
print(f"DIR imported {len(added)} objects directly "
      f"(meshes={sum(1 for o in added if o.type=='MESH')})")

from mathutils import Vector
lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
for o in added:
    if o.type != "MESH":
        continue
    mw = np.array(o.matrix_world)
    local = np.array([list(c) for c in o.bound_box], dtype=float)   # (8,3)
    corners = local @ mw[:3, :3].T + mw[:3, 3]
    lo = np.minimum(lo, corners.min(axis=0)); hi = np.maximum(hi, corners.max(axis=0))
print(f"  world bounds min={np.round(lo,2).tolist()}")
print(f"               max={np.round(hi,2).tolist()}")
print(f"  extents (m)  {np.round(hi-lo,2).tolist()}")

# --- flat background so real geometry is unmistakable ----------------------
renderer._set_background_color((0.0, 0.8, 0.0, 1.0))
renderer._set_ambient_light_color((0.75, 0.75, 0.75, 1.0))
centre = (lo + hi) / 2
span = float(np.max(hi - lo))
cam = kb.PerspectiveCamera(focal_length=28.0, sensor_width=36.0)
cam.position = tuple(centre + np.array([0.0, -span * 0.9, span * 0.45]))
cam.look_at(tuple(centre))
scene.camera = cam
print(f"  camera {tuple(round(v,1) for v in cam.position)} -> centre "
      f"{tuple(round(v,1) for v in centre)}  span {span:.1f} m")

out = renderer.render([0], return_layers=("rgba",))
img = np.array(out["rgba"], copy=True)[0]
rgb = img[..., :3].astype(int)
green = (rgb[..., 1] > 180) & (rgb[..., 0] < 80) & (rgb[..., 2] < 80)
print(f"  non-background coverage = {100*(1-green.mean()):.1f}%")
p = os.path.join(OUT, "direct_import.png")
cv2.imwrite(p, img[..., :3][..., ::-1])
print(f"  wrote {p}")
PY
