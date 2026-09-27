#!/usr/bin/env bash
# Watch the first sample until frames appear, then report lighting + brightness.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-1001/x1"

echo "waiting for frames..."
for i in $(seq 1 50); do
  n=$(ls "$D/rgb" 2>/dev/null | wc -l)
  c=$(ls "$REPO/cache/rolling/seed-001001/x1/images" 2>/dev/null | wc -l)
  if [ "$n" -ge 4 ] || [ "$c" -ge 4 ]; then
    echo "  frames ready after $((i*15))s (dataset rgb=$n cache images=$c)"
    break
  fi
  sleep 15
done

echo
echo "=== lighting ==="
grep -o "environment_lighting_source': '[a-z_+]*'" "$WS/tmp/t1_render.log" | tail -1 | sed 's/^/  /'
grep -o "environment_light_count': [0-9]*" "$WS/tmp/t1_render.log" | tail -1 | sed 's/^/  /'

echo
echo "=== brightness ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os, glob
import numpy as np
from PIL import Image
for c in ("/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-1001/x1",
          "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/cache/rolling/seed-001001/x1"):
    for sub in ("rgb", "images"):
        fs = sorted(glob.glob(os.path.join(c, sub, "*.png")))
        if not fs: continue
        print(f"  {sub}: {len(fs)} png")
        for f in fs[:3]:
            im = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
            print(f"    {os.path.basename(f)}: mean={im.mean():.2f} p50={np.percentile(im,50):.1f} "
                  f"p95={np.percentile(im,95):.1f} black={(im.max(axis=2)<8).mean():.3f}")
PY
