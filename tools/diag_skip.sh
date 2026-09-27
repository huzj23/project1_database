#!/usr/bin/env bash
# ===========================================================================
# BUG IN MY OWN RUNNER: rolling camC was reported "SKIP (complete)".
#
# The skip test only checks "video.mp4 exists and >= 81 rgb".  But
# datasets/rolling/seed-001001/x1 is the ORIGINAL clip rendered with the OLD
# trajectory_side camera the user REJECTED.  So the skip silently kept the bad clip
# and the new camera C was never rendered at all.
#
# Verify that diagnosis against the metadata (which records the camera that was
# actually used), then remove ONLY that sample and re-render with camera C.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== what camera did the EXISTING rolling clip use? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -20
import json, os
d = "datasets/rolling/seed-001001/x1"
if not os.path.isdir(d):
    print("  no existing sample"); raise SystemExit
m = json.load(open(d + "/metadata.json"))
R = m.get("render", {})
C = m.get("camera", {})
print(f"  camera_position = {R.get('camera_position')}")
print(f"  camera_focal    = {R.get('camera_focal_length_mm')}")
print(f"  camera block    = { {k: v for k, v in C.items() if k in ('position','look_at','focal_length_mm')} }")
print(f"  framing mode    = {C.get('framing', {}).get('mode') if isinstance(C.get('framing'), dict) else None}")
print(f"  rgb frames      = {len(os.listdir(d + '/rgb')) if os.path.isdir(d + '/rgb') else 0}")
print(f"  mtime           = {os.path.getmtime(d + '/metadata.json'):.0f}")
pos = R.get("camera_position")
if pos:
    isC = (abs(pos[0]+0.6744) < 1e-2 and abs(pos[1]+3.1931) < 1e-2 and abs(pos[2]-0.6127) < 1e-2)
    print(f"  is camera C? {isC}")
    if not isC:
        print("  -> CONFIRMED: this is the OLD rejected camera; it must be re-rendered")
PY

echo
echo "=== damping status ==="
cat "$WS/tmp/t1c_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
pgrep -af generate.py | head -1 | sed 's/^/  running: /'
