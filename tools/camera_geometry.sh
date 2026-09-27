#!/usr/bin/env bash
# Get the camera indoors by geometry, not by guessing.
#
# From the recorded framing report:
#   content_height 0.877 m  (vertical trajectory 0.448 + object 0.268 + padding)
#   trajectory_frame_fraction 0.62  ->  frame height must be 1.414 m
#   with a 50 mm lens that implies 3.49 m of stand-off, which lands outside
#   the room (x = 5.35 > 4.58).
#
# Stand-off scales linearly with (content_height / frame_fraction) / tan(vfov/2).
# Two levers, both legitimate:
#   * wider lens   50 mm -> 35 mm   (vfov grows ~1.43x)
#   * let content fill more of the frame  0.62 -> 0.78
# Combined: 0.877/0.78 = 1.124 m frame height; with 35 mm the ratio is
# 0.579 m of frame height per metre of distance -> 1.94 m stand-off.
# Camera then sits near (4.2, -4.3), inside the room.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"focal_length_mm:\s*[0-9.]+", "focal_length_mm: 35.0", t)
t = re.sub(r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.78", t)
# keep the object from dominating now that we are closer
t = re.sub(r"max_object_frame_fraction:\s*[0-9.]+", "max_object_frame_fraction: 0.55", t)
p.write_text(t)
c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
print("  focal_length_mm          :", c["camera"].get("focal_length_mm"))
print("  trajectory_frame_fraction:", fr.get("trajectory_frame_fraction"))
print("  max_object_frame_fraction:", fr.get("max_object_frame_fraction"))
PY

echo
echo "=== expected stand-off ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import math
content_h = 0.877
frac = 0.78
sensor_w, focal = 36.0, 35.0
aspect = 16/9
sensor_h = sensor_w / aspect
frame_h = content_h / frac
d = frame_h / (2 * math.tan(math.atan(sensor_h / (2 * focal))))
print(f"  frame height needed : {frame_h:.3f} m")
print(f"  stand-off           : {d:.3f} m   (room allows ~4.5 m before the wall)")
PY

echo
echo "=== run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -26
