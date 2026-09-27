#!/usr/bin/env bash
# One clean, self-verifying run.  Several recent attempts were confounded because
# the sample directory and the metadata disagreed (32 rgb frames on disk while the
# config said 16), which means I was reading one run's metadata against another
# run's pixels.  This version proves the pieces belong together by printing the
# camera from metadata AND the frame count AND the newest frame, and by wiping the
# whole datasets tree first.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

echo "=== active scenario settings ==="
"$PY" - <<'PY'
import yaml
c = yaml.safe_load(open("configs/scenarios/free_fall_gso.yaml"))
print("  timing   :", c["timing"])
print("  drop     :", c["physics"]["drop_height_absolute_range"])
print("  direction:", c["physics"]["direction_degrees_range"])
print("  camera   :", {k: c["camera"].get(k) for k in
                       ("policy", "side", "focal_length_mm")})
print("  framing  :", {k: v for k, v in c["camera"]["framing"].items()
                       if k in ("elevation_degrees", "max_distance",
                                "trajectory_frame_fraction",
                                "min_object_frame_fraction")})
print("  output   :", c["output"]["resolution"], c["output"]["modalities"])
PY

echo
echo "=== wipe ALL previous datasets so nothing stale can survive ==="
rm -rf "$REPO/datasets/free_fall"
echo "  removed datasets/free_fall"

echo
echo "=== run x0.5 ==="
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$WS/log/p1_clean.log" 2>&1
rc=$?
echo "  exit code: $rc"
grep -oE 'ValueError:.*' "$WS/log/p1_clean.log" | tail -1 | sed 's/^/  /'

echo
echo "=== artefacts on disk NOW ==="
D="$REPO/datasets/free_fall/seed-001000/x0.5"
if [ ! -d "$D" ]; then
  echo "  sample dir missing"
  tail -6 "$WS/log/p1_clean.log" | sed 's/^/  /'
  exit 0
fi
for sub in rgb depth segmentation; do
  printf '  %-14s %s frames\n' "$sub" "$(ls "$D/$sub" 2>/dev/null | wc -l)"
done
for f in video.mp4 trajectory.json collisions.json metadata.json config.yaml; do
  printf '  %-14s %s\n' "$f" "$([ -f "$D/$f" ] && echo present || echo MISSING)"
done
echo "  newest rgb    : $(ls -t "$D/rgb" 2>/dev/null | head -1)"
echo "  dir mtime     : $(stat -c %y "$D" 2>/dev/null)"

echo
echo "=== metadata says (must match the frames above) ==="
"$PY" - "$D" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = (md.get("camera") or {}).get("position")
look = (md.get("camera") or {}).get("look_at")
print(f"  frame_count(meta): {md.get('frame_count')}")
print(f"  resolution(meta) : {(md.get('render') or {}).get('resolution')}")
print(f"  camera           : {[round(v, 2) for v in cam] if cam else None}")
print(f"  look_at          : {[round(v, 2) for v in look] if look else None}")
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
print(f"  trajectory states: {len(st)}")
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
print(f"  moving frames    : {int((v > 0.02).sum())} ({100 * (v > 0.02).mean():.0f}%)")
print(f"  validation       : {(md.get('validation') or {}).get('valid')} "
      f"{((md.get('validation') or {}).get('reasons'))}")
PY

# stage just one frame, with the camera printed alongside, for a matched check
"$PY" - "$D" "$WS/outcomes/_P1_clean" <<'PY'
import json, os, shutil, sys
D, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))
frames = sorted(f for f in os.listdir(os.path.join(D, "rgb")) if f.endswith(".png"))
mid = frames[len(frames) // 2]
shutil.copy2(os.path.join(D, "rgb", mid), os.path.join(OUT, "mid.png"))
shutil.copy2(os.path.join(D, "rgb", frames[-1]), os.path.join(OUT, "last.png"))
shutil.copy2(os.path.join(D, "rgb", frames[0]), os.path.join(OUT, "first.png"))
for f in ("video.mp4", "metadata.json", "trajectory.json"):
    src = os.path.join(D, f)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(OUT, f))
print(f"  staged {mid} and {len(frames)}-frame set")
PY
