#!/usr/bin/env bash
# Clean, self-contained smoke run.
#
# Two problems with the previous attempts:
#   * the log went to /tmp, which the safety guard forbids referencing, so I was
#     reading a stale copy and misdiagnosing;
#   * DatasetWriter uses mkdir(exist_ok=False), so any leftover sample dir makes
#     the run fail at save time AFTER the expensive render.
# This version keeps the log in the workspace and always clears the target first.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
D="$REPO/datasets/free_fall/seed-001000/x1"
cd "$REPO" || exit 1

echo "=== clean target ==="
rm -rf "$D"
echo "  cleared $D"

echo
echo "=== run (log: $LOG) ==="
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x1 > "$LOG" 2>&1
rc=$?
echo "  exit code: $rc"

echo
echo "=== validation ==="
"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import json, os, sys
D = sys.argv[1]
p = os.path.join(D, "metadata.json")
if not os.path.isfile(p):
    print("  metadata.json missing -> run did not complete")
    raise SystemExit(0)
md = json.load(open(p))
val = md.get("validation") or {}
print(f"  valid   : {val.get('valid')}")
print(f"  reasons : {val.get('reasons')}")
for k, v in (val.get("metrics") or {}).items():
    if isinstance(v, float):
        print(f"    {k:<34} {v:.5f}")
    else:
        print(f"    {k:<34} {v}")
cam = md.get("camera") or {}
cp = cam.get("position")
print(f"  camera  : {cp}")
if cp:
    x, y, _ = cp
    print(f"  indoors : {-2.68 <= x <= 4.58 and -8.16 <= y <= 4.89}")
for name in ("video.mp4", "trajectory.json", "collisions.json", "config.yaml"):
    q = os.path.join(D, name)
    print(f"  {name:<18} {'ok' if os.path.isfile(q) else 'MISSING'}")
for sub in ("rgb", "depth", "segmentation"):
    print(f"  {sub:<18} {len(os.listdir(os.path.join(D, sub))) if os.path.isdir(os.path.join(D, sub)) else 0} frames")
PY

echo
echo "=== errors in log (if any) ==="
grep -nE 'Traceback|Error:|FileExists' "$LOG" | tail -6 | sed 's/^/  /' || echo "  none"
