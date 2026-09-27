#!/usr/bin/env bash
# Why the camera never moved: `trajectory_side` derives its azimuth from the
# SIMULATED trajectory, not from physics.direction_degrees_range.  A vertical drop
# has essentially no horizontal direction, so the policy picks the same side every
# time and my config change had no effect.
#
# The mentor provides a second policy, `camera.policy: random`, which "samples the
# full azimuth range while still looking at and framing the trajectory".  Switch
# to it and sweep seeds, recording the azimuth each draws, so we can pick one that
# puts the room's furniture behind the subject.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"policy:\s*\w+", "policy: random", t)
# the random policy needs an explicit azimuth range
if "azimuth_offset_degrees_range" in t:
    t = re.sub(r"azimuth_offset_degrees_range:\s*\[[^\]]*\]",
               "azimuth_offset_degrees_range: [-180.0, 180.0]", t)
p.write_text(t)
c = yaml.safe_load(open(p))
print("  camera policy:", c["camera"].get("policy"))
print("  azimuth range:", c["camera"].get("azimuth_offset_degrees_range"))
PY

echo
echo "=== seed sweep; record camera pose and which way it looks ==="
rm -rf "$REPO/datasets/free_fall"
for seed in 1000 1001 1002 1003 1004 1005; do
  "$BL" --background --factory-startup --python scripts/generate.py -- \
    --config configs/server.yaml --seed $seed --variant x0.5 \
    > "$WS/log/sw_$seed.log" 2>&1
  D="$REPO/datasets/free_fall/seed-00$seed/x0.5"
  if [ ! -f "$D/metadata.json" ]; then
    printf '  seed %-5s FAILED  %s\n' "$seed" \
      "$(grep -oE 'ValueError:.*' "$WS/log/sw_$seed.log" | tail -1 | cut -c1-90)"
    continue
  fi
  "$WS/tools/conda_env/bin/python" - "$D" "$seed" <<'PY'
import json, os, sys, math
import numpy as np
D, seed = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = np.array((md.get("camera") or {}).get("position"))
look = np.array((md.get("camera") or {}).get("look_at"))
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
ctr = (c.max(axis=0) + c.min(axis=0)) / 2
d = ctr - cam
az = (math.degrees(math.atan2(d[1], d[0])) + 360) % 360
zf = c[0, 2]
print(f"  seed {seed:<5} cam=({cam[0]:6.2f},{cam[1]:6.2f},{cam[2]:5.2f}) "
      f"drop=({zf:.2f}) view_az={az:5.1f} standoff={np.linalg.norm(cam-ctr):.2f}")
PY
done
