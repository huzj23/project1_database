#!/usr/bin/env bash
# Put the camera INSIDE the room.
#
# His camera is placed perpendicular to the trajectory:
#     side = (-direction[1], direction[0]);  if side == "right": side *= -1
#     camera = trajectory_centre + side * distance
# so its position depends on the sampled motion direction.  With a random
# direction over 360 degrees some draws put the lens outside the apartment, which
# is why we kept rendering an exterior wall.
#
# The floor corridor runs x[2.20,3.20] y[-4.30,1.10] inside a room spanning
# x[-2.68,4.58].  Holding the motion near +Y and taking side="left" puts the
# camera at roughly (centre_x - distance, centre_y) = (-0.8, -1.6): comfortably
# indoors.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
lines = p.read_text().splitlines()

out = []
seen_side = seen_dir = False
for l in lines:
    s = l.strip()
    if s.startswith("side:"):
        out.append("  side: left")
        seen_side = True
        continue
    if s.startswith("direction_degrees_range:"):
        out.append("  direction_degrees_range: [85.0, 95.0]")
        seen_dir = True
        continue
    out.append(l)

# insert if missing entirely
if not seen_dir:
    for i, l in enumerate(out):
        if l.strip().startswith("angular_speed_range:"):
            out.insert(i + 1, "  direction_degrees_range: [85.0, 95.0]")
            break

p.write_text("\n".join(out) + "\n")
c = yaml.safe_load(open(p))
print("  camera.side            :", c["camera"].get("side"))
print("  physics.direction_range:", c["physics"].get("direction_degrees_range"))
print("  camera.framing.max_dist:", c["camera"]["framing"].get("max_distance"))
PY

echo
echo "=== run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -30
