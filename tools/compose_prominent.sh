#!/usr/bin/env bash
# Compose so the subject is PROMINENT but the room is still readable.
#
# The survey (tools/find_blockers.sh) found azimuth 0 deg at elevation 28 deg has
# ZERO occluders along the whole fall, from a camera at (2.81, -4.30, 0.96).
#
# To force that azimuth:  his camera sits at  centre + side * distance, with
#     side = (-direction[1], direction[0])  flipped when side == "right"
# so side = (+1, 0) -- i.e. +X, azimuth 0 -- requires direction = (0, -1),
# angle -90 deg, with side: left.
#
# Subject prominence follows from  object / frame_width, and frame_width is set by
# the trajectory that must fit.  A shorter drop leaves relatively more room for
# the subject:
#     drop 0.94 m -> subject ~8.6% of frame width
#     drop 0.35 m -> subject ~20%  (target)
# The fall is kept visible by using the x0.5 gravity variant (slow motion) and a
# clip length matched to it.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml, math
repo = pathlib.Path(sys.argv[1])

# --- camera direction: force azimuth 0 (the verified-clear one) -------------
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
subs = [
    (r"direction_degrees_range:\s*\[[^\]]*\]", "direction_degrees_range: [-90.0, -90.0]"),
    (r"(\n\s*side:\s*)\w+", r"\g<1>left"),
    (r"drop_height_absolute_range:\s*\[[^\]]*\]", "drop_height_absolute_range: [0.30, 0.42]"),
    (r"drop_height_object_extent_range:\s*\[[^\]]*\]", "drop_height_object_extent_range: [1.2, 1.8]"),
    (r"min_drop_height:\s*[0-9.]+", "min_drop_height: 0.22"),
    (r"min_drop_distance:\s*[0-9.]+", "min_drop_distance: 0.25"),
    (r"frame_count:\s*\d+", "frame_count: 16"),
    (r"duration_seconds:\s*[0-9.]+", "duration_seconds: 1.0"),
    (r"focal_length_mm:\s*[0-9.]+", "focal_length_mm: 50.0"),
    (r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.85"),
    (r"object_padding:\s*[0-9.]+", "object_padding: 0.18"),
    (r"min_object_frame_fraction:\s*[0-9.]+", "min_object_frame_fraction: 0.15"),
    (r"max_object_frame_fraction:\s*[0-9.]+", "max_object_frame_fraction: 0.60"),
    (r"elevation_degrees:\s*[0-9.]+", "elevation_degrees: 28.0"),
    (r"horizontal_speed_range:\s*\[[^\]]*\]", "horizontal_speed_range: [0.0, 0.0]"),
]
for pat, rep in subs:
    t = re.sub(pat, rep, t)
p.write_text(t)

c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
print("  direction :", c["physics"]["direction_degrees_range"], " side:", c["camera"].get("side"))
print("  drop      :", c["physics"]["drop_height_absolute_range"])
print("  clip      :", c["timing"]["frame_count"], "frames @", c["timing"]["video_fps"], "fps")
print("  focal     :", c["camera"]["focal_length_mm"], "mm  elevation:", fr["elevation_degrees"])
print("  traj frac :", fr["trajectory_frame_fraction"], " obj padding:", fr["object_padding"])
for g, tag in ((9.81, "x1"), (4.905, "x0.5")):
    T = math.sqrt(2 * 0.36 / g)
    print(f"  gravity {tag:<5}: 0.36 m fall = {T:.2f} s = {T*c['timing']['video_fps']:.1f} frames"
          f"  ({100*T*c['timing']['video_fps']/c['timing']['frame_count']:.0f}% of the clip)")
PY

echo
echo "=== run x0.5 ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
rm -rf "$REPO/datasets/free_fall/seed-001000"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$LOG" 2>&1
echo "  exit code: $?"
grep -oE 'ValueError:.*' "$LOG" | tail -1 | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-001000/x0.5" <<'PY'
import json, os, sys, math
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("  metadata.json missing"); raise SystemExit
md = json.load(open(p))
cam = np.array((md.get("camera") or {}).get("position"))
look = np.array((md.get("camera") or {}).get("look_at"))
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
ctr = (c.max(axis=0) + c.min(axis=0)) / 2
d = ctr - cam
az = (math.degrees(math.atan2(d[1], d[0])) + 360) % 360
print(f"  camera     : ({cam[0]:.2f},{cam[1]:.2f},{cam[2]:.2f})")
print(f"  view azim  : {az:.0f} deg   (target 0 = verified clear)")
print(f"  stand-off  : {np.linalg.norm(cam - ctr):.2f} m")
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
print(f"  frames     : {len(st)}  moving={100 * (v > 0.02).mean():.0f}%")
print(f"  valid      : {(md.get('validation') or {}).get('valid')}")
PY
