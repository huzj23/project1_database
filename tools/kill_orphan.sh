#!/usr/bin/env bash
# Two generate.py processes are rendering the SAME sample (seed 1001) into the
# same cache dir -- the orphan from the earlier t1 session plus the probe.  That
# is exactly the stale-frame hazard, so keep only the probe and inspect the cache.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== process tree ==="
for pid in $(pgrep -f "generate.py"); do
  echo "  pid=$pid ppid=$(ps -o ppid= -p $pid | tr -d ' ') start=$(ps -o lstart= -p $pid)"
done

echo
echo "=== kill the orphan (the one whose parent is gone) ==="
for pid in $(pgrep -f "generate.py"); do
  ppid=$(ps -o ppid= -p $pid | tr -d ' ')
  # an orphan is reparented to init/systemd (ppid 1)
  if [ "$ppid" = "1" ]; then
    echo "  killing orphan pid=$pid"
    kill -9 "$pid" 2>/dev/null
  fi
done
sleep 2
echo "  remaining generate.py: $(pgrep -cf generate.py)"

echo
echo "=== frames staged in cache ==="
C="$REPO/cache/rolling/seed-001001/x1"
for sub in rgb depth segmentation; do
  echo "  $sub: $(ls $C/$sub 2>/dev/null | wc -l)"
done
ls "$C" 2>/dev/null | head -8 | sed 's/^/    /'

echo
echo "=== brightness of staged frames ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os, glob
import numpy as np
from PIL import Image
c = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/cache/rolling/seed-001001/x1"
for sub in ("rgb", "depth", "segmentation"):
    fs = sorted(glob.glob(os.path.join(c, sub, "*")))
    if not fs:
        print(f"  {sub}: none"); continue
    print(f"  {sub}: {len(fs)} files")
    for f in fs[:3]:
        im = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
        print(f"    {os.path.basename(f)}: mean={im.mean():.2f} "
              f"p50={np.percentile(im,50):.1f} p95={np.percentile(im,95):.1f} "
              f"black={(im.max(axis=2)<8).mean():.3f}")
PY
