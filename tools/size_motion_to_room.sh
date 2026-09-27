#!/usr/bin/env bash
# The indoor map cannot host a 0.9 m drop plus 0.9 m of travel: framing that needs
# a 4.20 m camera stand-off, which does not fit in a room, and the mentor's camera
# correctly REFUSES to distort itself -- it raises instead of silently producing a
# bad shot.  That is the behaviour we want, so the fix is to size the MOTION to
# the space, not to widen the camera envelope.
#
# His classroom map does exactly this for its table-top group: small objects get
# short travel and a close camera.  Follow that precedent.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()

subs = [
    (r"drop_height_object_extent_range:\s*\[[^\]]*\]",
     "drop_height_object_extent_range: [1.5, 2.6]"),
    (r"drop_height_absolute_range:\s*\[[^\]]*\]",
     "drop_height_absolute_range: [0.22, 0.45]"),
    (r"horizontal_speed_range:\s*\[[^\]]*\]",
     "horizontal_speed_range: [0.01, 0.05]"),
    (r"vertical_speed_range:\s*\[[^\]]*\]",
     "vertical_speed_range: [-0.02, 0.02]"),
    (r"angular_speed_range:\s*\[[^\]]*\]",
     "angular_speed_range: [0.0, 1.0]"),
    (r"min_drop_height:\s*[0-9.]+", "min_drop_height: 0.15"),
    (r"min_drop_distance:\s*[0-9.]+", "min_drop_distance: 0.12"),
    (r"max_distance:\s*[0-9.]+", "max_distance: 3.10"),
    (r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.62"),
]
for pat, rep in subs:
    t = re.sub(pat, rep, t)
p.write_text(t)

c = yaml.safe_load(open(p))
print("  physics:")
for k in ("drop_height_absolute_range", "horizontal_speed_range",
          "vertical_speed_range", "angular_speed_range"):
    print(f"    {k:<32} {c['physics'].get(k)}")
print("  validation:")
for k in ("min_drop_height", "min_drop_distance", "max_surface_penetration",
          "require_bounce"):
    print(f"    {k:<32} {c['validation'].get(k)}")
print("  camera framing:")
for k in ("min_distance", "max_distance", "trajectory_frame_fraction",
          "min_object_frame_fraction", "max_object_frame_fraction"):
    print(f"    {k:<32} {c['camera']['framing'].get(k)}")
PY

echo
echo "=== run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -26
