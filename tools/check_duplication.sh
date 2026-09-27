#!/usr/bin/env bash
# Are the 32 rendered frames actually the requested 16, duplicated?
#
# The instrumentation showed:
#     render_frames=16  (frames = [1..16])
#     rendered rgba=(32, ...)
# so Kubric returned twice as many frames as were asked for.  If the second half
# duplicates the first, every clip we have produced shows the motion TWICE and the
# metadata (16 states) describes only half the video.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x0.5"

echo "=== hash every rgb frame, look for a repeat pattern ==="
"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import hashlib, os, sys
D = sys.argv[1]
rgb = os.path.join(D, "rgb")
names = sorted(f for f in os.listdir(rgb) if f.endswith(".png"))
h = {}
for n in names:
    with open(os.path.join(rgb, n), "rb") as fh:
        h[n] = hashlib.sha256(fh.read()).hexdigest()[:12]
print(f"  frames: {len(names)}")
for n in names:
    print(f"    {n}  {h[n]}")

half = len(names) // 2
first = [h[n] for n in names[:half]]
second = [h[n] for n in names[half:]]
print()
print(f"  first half  == second half ? {first == second}")
dup = sum(1 for a, b in zip(first, second) if a == b)
print(f"  positionally matching pairs: {dup} / {half}")

# also: how many DISTINCT frames are there?
print(f"  distinct frames: {len(set(h.values()))} of {len(names)}")
PY
