#!/usr/bin/env bash
# Re-package the smoke sample after the camera fix, and report the camera pose so
# we can confirm it is now INSIDE the room (x within [-2.68, 4.58]).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"
OUT="$WS/outcomes/_P1_smoke"
rm -rf "$OUT"; mkdir -p "$OUT"

cp -f "$D/video.mp4" "$D/trajectory.json" "$D/collisions.json" \
      "$D/metadata.json" "$D/config.yaml" "$OUT/" 2>/dev/null

"$PY" - "$D" "$OUT" <<'PY'
import json, os, shutil, sys
D, OUT = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))

def dig(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None

cam = dig(md, "camera") or {}
cp = cam.get("position") or dig(md, "camera_position")
print(f"  camera position : {cp}")
print(f"  focal length    : {cam.get('focal_length') or cam.get('focal_length_mm')}")
val = dig(md, "validation") or {}
print(f"  validation      : valid={val.get('valid')} reasons={val.get('reasons')}")

if cp:
    x, y, z = cp
    inside = -2.68 <= x <= 4.58 and -8.16 <= y <= 4.89
    print(f"  inside the room : {inside}   (room x[-2.68,4.58] y[-8.16,4.89])")

# copy a spread of frames
for i in (0, 5, 10, 20, 35, 50, 70, 80):
    for cand in (f"rgb_{i:05d}.png", f"rgb_{i+1:05d}.png"):
        src = os.path.join(D, "rgb", cand)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, f"frame_{i:05d}.png"))
            break
print("  frames copied")
PY

echo
echo "=== packaged ==="
ls "$OUT" | sed 's/^/  /'
echo "  total: $(du -sh "$OUT" | cut -f1)"
