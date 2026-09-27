#!/usr/bin/env bash
# Apply the measured line-of-sight result.
#
# Probe (tools/line_of_sight.sh) cast rays from a ring of camera positions to the
# subject and counted unobstructed ones:
#     elev 12 -> 13/24 clear
#     elev 20 -> 15/24
#     elev 28 -> 17/24
#     elev 36 -> 18/24   clear azimuths ~0-150 and ~255-345 (blocked ~165-240)
#     elev 45 -> 18/24
# So the camera must look DOWN over the furniture, which is the "raise the camera"
# half of the agreed fix.
#
# The azimuth itself is policy-chosen, so this run also prints which azimuth it
# picked, to confirm it landed in a clear band.
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
t = re.sub(r"elevation_degrees:\s*[0-9.]+", "elevation_degrees: 36.0", t)
t = re.sub(r"min_height_above_trajectory:\s*[0-9.]+", "min_height_above_trajectory: 0.60", t)
p.write_text(t)
c = yaml.safe_load(open(p))
fr = c["camera"]["framing"]
print(f"  elevation     : {fr['elevation_degrees']} deg")
print(f"  min height    : {fr['min_height_above_trajectory']} m above trajectory")
d, s = 2.05, math.radians(fr["elevation_degrees"])
print(f"  camera height : {0.0007 + d * math.sin(s):.2f} m  (tables ~0.75, sofas ~0.8)")
PY

echo
echo "=== run x0.5, seed 1000 ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
LOG="$WS/log/p1_smoke.log"
rm -rf "$REPO/datasets/free_fall/seed-001000"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$LOG" 2>&1
echo "  exit code: $?"
grep -oE 'ValueError:.*' "$LOG" | tail -1 | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" - "$REPO/datasets/free_fall/seed-001000/x0.5" <<'PY'
import json, os, sys
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
az = (math.degrees(math.atan2(d[1], d[0])) + 360) % 360 if (math := __import__("math")) else 0
print(f"  camera      : ({cam[0]:.2f}, {cam[1]:.2f}, {cam[2]:.2f})")
print(f"  look-at     : ({look[0]:.2f}, {look[1]:.2f}, {look[2]:.2f})")
print(f"  view azimuth: {az:.0f} deg   (clear bands: 0-150 and 255-345)")
print(f"  cam height  : {cam[2]:.2f} m")
print(f"  stand-off   : {np.linalg.norm(cam - ctr):.2f} m")
print(f"  look-down   : {math.degrees(math.asin((cam[2] - look[2]) / np.linalg.norm(cam - look))):.1f} deg")
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
print(f"  frames      : {len(st)}  moving={int((v > 0.02).sum())} ({100 * (v > 0.02).mean():.0f}%)")
print(f"  valid       : {(md.get('validation') or {}).get('valid')}")
PY
