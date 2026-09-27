#!/usr/bin/env bash
# CONCEPT: realistic physics clip = GSO scanned object + ReplicaCAD interior
# + object RESTING ON THE FLOOR + real contact shadow + sensible framing.
#
# Tests the three fixes for the "fake" look:
#   1. background texel density / real 3D scene instead of a flat cyclorama
#   2. object grounded on the floor (rest height from data.json bounds)
#   3. subject framed to a sensible share of the frame
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1
OUT="$WS/outcomes/_concept"
rm -rf "$OUT"

"$PY" - "$OUT" <<'PY' 2>&1 | grep -E '^CONCEPT|^  '
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_motions as pm
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import cv2, bpy

WS = "/data/raw/huzijian/project1_database"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

GSO_NAME = "Sootheze_Cold_Therapy_Elephant"
GSO_DIR = os.path.join(WS, "models/gso", GSO_NAME)
d = json.load(open(os.path.join(GSO_DIR, "data.json")))
b = d["kwargs"]["bounds"]
rest_z = -b[0][2]                      # lowest point back to the floor
span = (b[1][0] - b[0][0], b[1][1] - b[0][1], b[1][2] - b[0][2])
print(f"CONCEPT object {GSO_NAME}")
print(f"  span {span[0]:.3f} x {span[1]:.3f} x {span[2]:.3f} m   rest_z={rest_z:.3f}")

N, FPS = 24, 24
scratch = tempfile.mkdtemp(prefix="concept_")
scene = kb.Scene(resolution=(1280, 720), frame_start=0, frame_end=N - 1,
                 frame_rate=FPS, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=32, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
print("  views ok")

# --- backdrop: photoreal ReplicaCAD interior, render-only -------------------
if not pb.build_interior(kb, scene, renderer,
                         pb.InteriorSpec(stage="frl_apartment_stage",
                                         hdri="empty_warehouse_01",
                                         hdri_strength=0.6,
                                         fill_intensity=220.0,
                                         motion_blur_shutter=0.25)):
    raise SystemExit("backdrop failed")
print("  interior backdrop ok")

# --- the actor: a real scanned GSO object, RESTING ON THE FLOOR -------------
obj = kb.FileBasedObject(
    name=GSO_NAME,
    simulation_filename=os.path.join(GSO_DIR, "object.urdf"),
    render_filename=os.path.join(GSO_DIR, "visual_geometry.obj"),
    bounds=tuple(tuple(v) for v in b),
    mass=d["kwargs"]["mass"],
    scale=1.0,
    position=(0.0, 0.0, rest_z),        # <- grounded, not floating
    segmentation_id=2,
)
try:
    obj.material = kb.PrincipledBSDFMaterial(color=(0.85, 0.55, 0.35, 1.0))
except Exception:
    pass
scene += obj
print(f"  actor added at z={rest_z:.3f} (on the floor)")

# --- motion: small circle at floor level so it slides on the ground ---------
spec = pm.CircularSpec(radius=0.45, period_s=6.0,
                       center=(0.0, 0.0, rest_z), axis="z", spin_per_orbit=1.0)
states = pm.apply_circular(kb, obj, spec, N, float(FPS), [0.0, 0.0, 0.0])
print(f"  motion: r={spec.radius} m  v={spec.tangential_speed:.2f} m/s")

# --- framing: subject + its path, no clamps --------------------------------
traj = []
for f in range(N):
    p = states[f]["position"]
    for dx, dy, dz in ((0, 0, span[2] / 2), (0, 0, -span[2] / 2),
                       (span[0] / 2, 0, 0), (-span[0] / 2, 0, 0)):
        traj.append([p[0] + dx, p[1] + dy, p[2] + dz])
cam_d, fr = pc.auto_frame_camera(
    kb, scene, traj, (0.0, 0.0, rest_z + span[2] * 0.4),
    elevation_deg=13.0, azimuth_deg=-58.0, margin=0.16,
    start_distance=2.0, focal_length=55.0, sensor_width=36.0)
print(f"  camera d={cam_d:.2f} m  span=({fr.get('final_span_x',0):.2f},"
      f"{fr.get('final_span_y',0):.2f})")

out = renderer.render(list(range(N)), return_layers=("rgba", "segmentation", "depth"))
out = {k: np.array(v, copy=True) for k, v in out.items()}
print("  rendered")
rgba = pc.prepare_rgba(out["rgba"])
pc.write_image_sequence(rgba, OUT, "rgba", "png")
print(f"CONCEPT wrote {OUT}/rgba_00000.png ... ({len(rgba)} frames)")
PY

echo
ls -la "$OUT" | head -5
