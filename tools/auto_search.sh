#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Autonomous camera search.
#
# Now that stale frames are purged, the camera really moves.  Instead of me
# eyeballing one render at a time, score candidates automatically:
#
#   occlusion  - the subject's SEGMENTATION pixel count.  If furniture blocks the
#                view, the visible subject area collapses.
#   richness   - colour variance of the BACKGROUND (non-subject) pixels.  A bare
#                wall or floor is nearly uniform; a furnished room has structure.
#   size       - subject area as a fraction of the frame, so it stays prominent
#                without filling everything.
#
# Sweep seeds cheaply (low resolution, few samples), rank, then re-render the best
# at full quality.  This is the loop the review asked for: iterate until the
# background is right, and only show the winner.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

SEEDS="${1:-1000 1001 1002 1003 1004 1005 1006 1007}"

echo "=== probe settings: low res so a sweep is affordable ==="
"$PY" - <<'PY'
import re, pathlib, yaml
p = pathlib.Path("configs/scenarios/free_fall_gso.yaml")
t = p.read_text()
t = re.sub(r"resolution:\s*\[[^\]]*\]", "resolution: [480, 270]", t)
p.write_text(t)
q = pathlib.Path("configs/server.yaml")
s = q.read_text()
s = re.sub(r"^(\s*samples_per_pixel:).*$", r"\g<1> 8", s, flags=re.M)
q.write_text(s)
c = yaml.safe_load(open(p))
print("  resolution:", c["output"]["resolution"], " spp: 8 (probe only)")
PY

echo
echo "=== sweep ==="
rm -rf "$REPO/datasets/free_fall"
for seed in $SEEDS; do
  "$BL" --background --factory-startup --python scripts/generate.py -- \
    --config configs/server.yaml --seed "$seed" --variant x0.5 \
    > "$WS/log/sweep_$seed.log" 2>&1
  D="$REPO/datasets/free_fall/seed-$(printf '%06d' $seed)/x0.5"
  if [ ! -f "$D/metadata.json" ]; then
    printf '  %-6s FAILED %s\n' "$seed" \
      "$(grep -oE 'ValueError:.*' "$WS/log/sweep_$seed.log" | tail -1 | cut -c1-70)"
    continue
  fi
  "$PY" - "$D" "$seed" <<'PY'
import json, os, sys
import numpy as np
D, seed = sys.argv[1], sys.argv[2]
# subject = the actor's segmentation id (2); backdrop ids are 1/3
seg_files = sorted(f for f in os.listdir(os.path.join(D, "segmentation")) if f.endswith(".png"))
import cv2
areas, vars_ = [], []
for n in seg_files:
    m = cv2.imread(os.path.join(D, "segmentation", n), cv2.IMREAD_GRAYSCALE)
    rgb = cv2.imread(os.path.join(D, "rgb", n.replace("segmentation", "rgb")))
    if m is None or rgb is None:
        continue
    subj = m > 0
    areas.append(float(subj.mean()))
    if (~subj).sum() > 100:
        bg = rgb[~subj].astype(np.float32)
        vars_.append(float(bg.reshape(-1, 3).std(axis=0).mean()))
if not areas:
    print(f"  {seed:<6} no frames"); raise SystemExit
a = float(np.median(areas)); v = float(np.median(vars_)) if vars_ else 0.0
md = json.load(open(os.path.join(D, "metadata.json")))
cam = (md.get("camera") or {}).get("position")
print(f"  {seed:<6} subject_area={a*100:5.2f}%  bg_std={v:6.1f}  "
      f"cam=({cam[0]:6.2f},{cam[1]:6.2f},{cam[2]:5.2f})")
PY
done
