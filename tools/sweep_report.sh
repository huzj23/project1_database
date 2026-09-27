#!/usr/bin/env bash
# Report the azimuth sweep results (the sweep itself may still be running).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "running render procs: $(ps -eo cmd | grep -c '[g]enerate.py')"
echo
for seed in 1000 1001 1002 1003 1004 1005; do
  D="$REPO/datasets/free_fall/seed-00$seed/x0.5"
  if [ ! -f "$D/metadata.json" ]; then
    printf '  seed %-5s %s\n' "$seed" \
      "$(grep -oE 'ValueError:.*' "$WS/log/sw_$seed.log" 2>/dev/null | tail -1 | cut -c1-80)"
    continue
  fi
  "$WS/tools/conda_env/bin/python" - "$D" "$seed" <<'PY'
import json, os, sys, math
import numpy as np
D, seed = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = np.array((md.get("camera") or {}).get("position"))
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
ctr = (c.max(axis=0) + c.min(axis=0)) / 2
d = ctr - cam
az = (math.degrees(math.atan2(d[1], d[0])) + 360) % 360
print(f"  seed {seed:<5} cam=({cam[0]:6.2f},{cam[1]:6.2f},{cam[2]:5.2f}) "
      f"view_az={az:5.1f} standoff={np.linalg.norm(cam - ctr):.2f} "
      f"frames={len(st)}")
PY
done
