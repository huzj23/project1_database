#!/usr/bin/env bash
# ===========================================================================
# Apply the USER-CHOSEN camera C to the 匀速 clip and preflight it.
#
# User decision: "裁定匀速机位C，建议不要做特写，期待最后视频效果"
#   -> camera C = az270_d2.2, i.e. position (-0.6744, -3.1931, 0.6127) looking at
#      (-0.6744, -0.9931, 0.1027), focal 50 mm.
#      Chosen over A because it is FARTHER (objfrac 0.075 vs 0.090) -> a wide shot,
#      matching "不要做特写".  Trade-off, stated honestly: bike_02 IS inside this
#      frame, covering ~13.1% of the image at 3.5-4.9 m depth (right side, not the
#      left), so it reads as distant background rather than near-field clutter.
#
# Only ONE 匀速 clip is rendered ("最多再跑一条"), so the fabric cube is removed
# from selection.asset_ids -- it was the frictionless-sliding actor whose motion had
# no physical motivation.
#
# `fixed` is required here for the same reason as the turntable clips: the old
# `trajectory_side` policy derives the pose from each clip's own motion and so
# cannot reproduce a pose the user picked.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

F="configs/scenarios/rolling_gso.yaml"
[ -f "$F.pre_camC" ] || cp "$F" "$F.pre_camC"
echo "  backup: $F.pre_camC"

"$WS/tools/conda_env/bin/python" - "$F" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()

OLD_CAM = """camera:
  policy: trajectory_side
  relative_to_trajectory: true
  side: random
  azimuth_offset_degrees_range: [-25.0, 25.0]
  focal_length_mm: 40.0
  framing:
    sensor_width_mm: 36.0
    trajectory_frame_fraction: 0.80
    object_padding: 0.25
    min_object_frame_fraction: 0.03
    max_object_frame_fraction: 0.55
    min_object_frame_area_fraction: 0.0025
    max_object_frame_area_fraction: 0.20
    min_distance: 0.50
    max_distance: 8.00
    elevation_degrees: 12.0
    min_height_above_trajectory: 0.25
    look_at_offset: 0.0
"""

NEW_CAM = """camera:
  # ---------------------------------------------------------------------
  # CAMERA C -- chosen by the user ("裁定匀速机位C，建议不要做特写").
  #
  # The old `trajectory_side` pose sat at (-0.643, 0.800, 0.458), which is
  # 0.238 m from frl_apartment_bike_02 -- the camera was standing inside the
  # bicycle, so it filled the left of frame.  This pose is 3.53-4.86 m from that
  # bicycle and is the WIDER of the two candidates (object occupies 0.075 of the
  # frame width vs 0.090 for camera A), i.e. deliberately not a close-up.
  #
  # Measured coverage of the bicycle here: ~13.1% of the image, on the RIGHT,
  # 3.5-4.9 m away -> distant background, not near-field clutter.
  #
  # `fixed` uses the pose verbatim and injects no azimuth/side randomness, so the
  # framing cannot drift with seed or trajectory.
  # ---------------------------------------------------------------------
  policy: fixed
  position: [-0.6744, -3.1931, 0.6127]
  look_at: [-0.6744, -0.9931, 0.1027]
  focal_length_mm: 50.0
  framing:
    sensor_width_mm: 36.0
"""

if OLD_CAM not in s:
    raise SystemExit("FATAL: camera block not found verbatim; refusing to guess")
s = s.replace(OLD_CAM, NEW_CAM, 1)

OLD_ASSETS = """  asset_ids:
    - gso_whey_protein_vanilla
    - gso_room_essentials_fabric_cube_lavender
"""
NEW_ASSETS = """  asset_ids:
    # Only the ROLLING asset: the user asked for at most one more 匀速 clip, and
    # this is the only asset we own that can roll (cross-section r_cv 0.078 vs
    # 0.204-0.327 for every other asset), so it is the only one whose constant
    # velocity is physically motivated rather than an imposed frictionless slide.
    - gso_whey_protein_vanilla
"""
if OLD_ASSETS not in s:
    raise SystemExit("FATAL: asset_ids block not found verbatim; refusing to guess")
s = s.replace(OLD_ASSETS, NEW_ASSETS, 1)

open(p, "w").write(s)
print("  rewrote camera block -> fixed camera C")
print("  rewrote asset_ids    -> whey can only")
PY

echo
echo "=== YAML parses + pipeline loads it ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -25
import sys
sys.path.insert(0, "src")
import yaml
from physim.config import load_run_config
raw = yaml.safe_load(open("configs/scenarios/rolling_gso.yaml"))
print(f"  yaml ok: scenario={raw['scenario']} assets={raw['selection']['asset_ids']}")
print(f"  camera policy={raw['camera']['policy']} pos={raw['camera']['position']} "
      f"look={raw['camera']['look_at']} focal={raw['camera']['focal_length_mm']}")
print(f"  physics_fps={raw['timing']['physics_fps']} video_fps={raw['timing']['video_fps']} "
      f"frames={raw['timing']['frame_count']}")
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
print(f"  load_run_config ok; scenario_config resolved")
PY

echo
echo "=== PREFLIGHT seed 1001: sample -> simulate -> validate -> CAMERA ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import sys
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import fixed_camera
from physim.pipeline import _camera_config, object_extent

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
p = np.array([s.position for s in res.trajectory])
omg = np.array([s.angular_velocity for s in res.trajectory])
vlin = np.array([s.linear_velocity for s in res.trajectory])
sp = np.linalg.norm(vlin[:,:2], axis=1); om = np.linalg.norm(omg, axis=1)
slip = np.where(sp > 1e-6, om*smp.support_height/np.maximum(sp,1e-9), np.nan)
print(f"  valid={rep.valid} reasons={list(rep.reasons)}")
print(f"  quat={tuple(round(x,4) for x in smp.initial_quaternion)} support_h={smp.support_height:.5f}")
print(f"  travel={np.linalg.norm(p[-1]-p[0]):.4f} z={p[:,2].min():.5f}..{p[:,2].max():.5f}")
print(f"  slip={np.nanmin(slip):.4f}..{np.nanmax(slip):.4f} (1.0 = pure rolling)")
print(f"  speed={sp.min():.4f}..{sp.max():.4f} m/s")

camcfg = _camera_config(cfg, ms, smp)
cam = fixed_camera(res, camcfg)
print(f"  CAMERA pos={tuple(round(float(x),4) for x in cam.position)}")
print(f"         look={tuple(round(float(x),4) for x in cam.look_at)} focal={cam.focal_length_mm}")
print(f"         mode={cam.framing.get('mode')}")
ok = (abs(cam.position[0]-(-0.6744))<1e-3 and abs(cam.position[1]-(-3.1931))<1e-3
      and abs(cam.position[2]-0.6127)<1e-3)
print(f"  camera is EXACTLY camera C: {ok}")
# where does the trajectory land on screen?
import math
fwd = np.array(cam.look_at)-np.array(cam.position); fwd/=np.linalg.norm(fwd)
right = np.cross(fwd, np.array([0,0,1.0])); right/=np.linalg.norm(right)
up = np.cross(right, fwd)
fov_h = 2*math.atan(36.0/(2*cam.focal_length_mm)); fov_v = 2*math.atan((36.0*1080/1920)/(2*cam.focal_length_mm))
worst = 0.0
for pt in p[::8]:
    d = pt-np.array(cam.position); z=float(d@fwd)
    nx = math.atan2(float(d@right), z)/(fov_h/2); ny = math.atan2(float(d@up), z)/(fov_v/2)
    worst = max(worst, abs(nx), abs(ny))
print(f"  trajectory max |norm| on screen = {worst:.3f} (must be < 1.0 to stay in frame)")
PY
