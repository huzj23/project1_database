#!/usr/bin/env bash
# Rebalance so the object actually MOVES for most of the clip.
#
# I had the relationship backwards in the previous attempt.  Rendered frames of
# motion = (fall duration) x (video_fps).  LOWERING video_fps therefore REDUCES
# motion frames -- halving it cancelled the bigger drop, which is why the motion
# share never improved.
#
# Fall duration is T = sqrt(2h/g).  So to spend more of the clip moving:
#   * raise the drop (T grows as sqrt(h))
#   * LOWER effective gravity -> the mentor's own x0.5 variant does exactly this
#     and is a declared controlled variable, so it is a supported mechanism
#     rather than a hack
#   * shorten the clip so the fall is a larger share of it
#
# Camera constraint that caps the drop: the trajectory (~drop + object) must fit
# the frame while the object stays >= min_object_frame_fraction of the width.
# For an object 0.27 m with the subject at 10%, frame width <= 2.7 m -> frame
# height 1.52 m.  A 1.0 m drop (trajectory ~1.1 m) fits at ~73% of frame height;
# 1.5 m does not.  Hence drop ~1.0 m.
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
subs = [
    (r"drop_height_absolute_range:\s*\[[^\]]*\]", "drop_height_absolute_range: [0.85, 1.10]"),
    (r"drop_height_object_extent_range:\s*\[[^\]]*\]", "drop_height_object_extent_range: [3.5, 4.5]"),
    (r"min_drop_height:\s*[0-9.]+", "min_drop_height: 0.70"),
    (r"min_drop_distance:\s*[0-9.]+", "min_drop_distance: 0.75"),
    (r"video_fps:\s*\d+", "video_fps: 16"),
    (r"frame_count:\s*\d+", "frame_count: 32"),
    (r"duration_seconds:\s*[0-9.]+", "duration_seconds: 2.0"),
    # leave a little headroom on the subject-size floor
    (r"min_object_frame_fraction:\s*[0-9.]+", "min_object_frame_fraction: 0.085"),
    (r"max_distance:\s*[0-9.]+", "max_distance: 6.00"),
    (r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.78"),
]
for pat, rep in subs:
    t = re.sub(pat, rep, t)
p.write_text(t)

c = yaml.safe_load(open(p))
fps = c["timing"]["video_fps"]; n = c["timing"]["frame_count"]
print(f"  drop      : {c['physics']['drop_height_absolute_range']} m")
print(f"  clip      : {n} frames @ {fps} fps = {n/fps:.1f} s")
for g, tag in ((9.81, "x1 (normal)"), (4.905, "x0.5 (slow motion)")):
    T = math.sqrt(2 * 1.0 / g)
    frames = T * fps
    print(f"  gravity {tag:<20} fall of 1.0 m takes {T:.2f} s = {frames:.1f} frames"
          f"  -> {100*frames/n:.0f}% of the clip")
PY

echo
echo "=== run with the x0.5 gravity variant (slow motion) ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
rm -rf "$REPO/datasets/free_fall/seed-001000/x0.5"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$LOG" 2>&1
rc=$?
echo "  exit code: $rc"
echo
grep -oE 'SAMPLE_OUTPUT=.*' "$LOG" | tail -1 | sed 's/^/  /'
grep -oE 'ValueError:.*' "$LOG" | tail -1 | sed 's/^/  /'

echo
echo "=== validation for the x0.5 variant ==="
"$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-001000/x0.5" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("  metadata.json missing -> run did not complete"); raise SystemExit
md = json.load(open(p))
val = md.get("validation") or {}
print(f"  valid    : {val.get('valid')}  reasons={val.get('reasons')}")
m = val.get("metrics") or {}
for k in ("drop_distance", "max_surface_penetration", "supported_fraction",
          "collision_count", "max_linear_speed"):
    if k in m: print(f"    {k:<30} {m[k]}")
cam = (md.get("camera") or {}).get("position")
print(f"  camera   : {cam}")
if cam:
    x, y, _ = cam
    print(f"  indoors  : {-1.0 <= x <= 2.8 and -6.3 <= y <= -1.8}  (support region)")

tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
mv = v > 0.02
print(f"  frames   : {len(st)}  moving={int(mv.sum())} ({100*mv.mean():.0f}%)")
PY
