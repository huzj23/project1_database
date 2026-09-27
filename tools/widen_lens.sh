#!/usr/bin/env bash
# The stand-off is set by:  distance = (content_height / frame_fraction) / (frame height per metre)
# and "frame height per metre" = 2*tan(atan(sensor_h/(2*focal))).
#
# With a 35 mm lens and a 0.94 m drop that works out at ~3-4 m, which shoves the
# camera into the -Y wall (y = -8.06, room ends at -8.16) and fills the frame
# with wall and shelving.
#
# Shorten the stand-off by WIDENING THE LENS rather than shrinking the drop, so
# the longer fall (and its extra frames of motion) is preserved:
#     24 mm -> 0.84 m of frame height per metre of distance
#     content 1.4 m at fraction 0.80 -> frame height 1.75 m -> distance ~2.1 m
# 2.1 m fits comfortably inside the room around the open-region centre.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml, math
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"focal_length_mm:\s*[0-9.]+", "focal_length_mm: 24.0", t)
t = re.sub(r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.80", t)
t = re.sub(r"min_object_frame_fraction:\s*[0-9.]+", "min_object_frame_fraction: 0.070", t)
p.write_text(t)

c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
focal = c["camera"]["focal_length_mm"]
sensor_h = 36.0 / (16 / 9)
per_m = 2 * math.tan(math.atan(sensor_h / (2 * focal)))
content = 0.94 + 0.268 + 0.20
frame_h = content / fr["trajectory_frame_fraction"]
print(f"  focal            : {focal} mm")
print(f"  frame h per metre: {per_m:.3f} m")
print(f"  content height   : {content:.2f} m -> frame height {frame_h:.2f} m")
print(f"  expected standoff: {frame_h / per_m:.2f} m")
print(f"  object fraction  : {0.268 / (frame_h * 16 / 9):.3f}  (floor {fr['min_object_frame_fraction']})")
PY

echo
echo "=== run x0.5 ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
rm -rf "$REPO/datasets/free_fall/seed-001000/x0.5"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$LOG" 2>&1
echo "  exit code: $?"
grep -oE 'ValueError:.*' "$LOG" | tail -1 | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-001000/x0.5" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("  metadata.json missing"); raise SystemExit
md = json.load(open(p))
val = md.get("validation") or {}
print(f"  valid   : {val.get('valid')}  reasons={val.get('reasons')}")
m = val.get("metrics") or {}
for k in ("drop_distance", "max_surface_penetration", "collision_count"):
    if k in m:
        print(f"    {k:<26} {m[k]}")
cam = (md.get("camera") or {}).get("position")
print(f"  camera  : {[round(v, 2) for v in cam] if cam else None}")
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c0 = np.array([s["position"] for s in st])
c = (c0.max(axis=0) + c0.min(axis=0)) / 2
if cam:
    print(f"  standoff: {np.linalg.norm(np.array(cam) - c):.2f} m")
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
print(f"  frames  : {len(st)}  moving={int((v > 0.02).sum())} ({100 * (v > 0.02).mean():.0f}%)")
PY
