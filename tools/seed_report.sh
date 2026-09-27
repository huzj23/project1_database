#!/usr/bin/env bash
# Report the seed sweep results.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

for s in 1000 1001 1002; do
  D="$REPO/datasets/free_fall/seed-00$s/x0.5"
  printf 'seed %s: ' "$s"
  if [ -f "$D/metadata.json" ]; then
    "$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import json, os, sys
import numpy as np
D = sys.argv[1]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = (md.get("camera") or {}).get("position")
tr = json.load(open(os.path.join(D, "trajectory.json")))
st = tr if isinstance(tr, list) else tr.get("states", [])
c = np.array([s["position"] for s in st])
ctr = (c.max(axis=0) + c.min(axis=0)) / 2
v = np.linalg.norm(np.array([s["linear_velocity"] for s in st]), axis=1)
wx = min(cam[0] + 2.68, 4.58 - cam[0])
wy = min(cam[1] + 8.16, 4.89 - cam[1])
print(f"OK cam=({cam[0]:.2f},{cam[1]:.2f}) wall_clear={min(wx, wy):.2f}m "
      f"standoff={np.linalg.norm(np.array(cam) - ctr):.2f}m "
      f"moving={100 * (v > 0.02).mean():.0f}% "
      f"valid={(md.get('validation') or {}).get('valid')}")
PY
  else
    grep -oE 'ValueError:.*' "$WS/log/p1_seed$s.log" 2>/dev/null | tail -1
    [ -s "$WS/log/p1_seed$s.log" ] || echo "(no log)"
  fi
done
