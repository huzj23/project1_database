#!/usr/bin/env bash
# Probe-render status: lighting diagnostics + frame brightness.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/rolling/seed-1001/x1"

echo "=== rgb frames ==="
ls "$D/rgb" 2>/dev/null | wc -l

echo "=== lighting diagnostics ==="
grep -o "environment_lighting_source': '[a-z_+]*'" "$WS/tmp/probe_render.log" | tail -1
grep -o "environment_light_count': [0-9]*" "$WS/tmp/probe_render.log" | tail -1
grep -o "environment_light_types': \[[^]]*\]" "$WS/tmp/probe_render.log" | tail -1
grep -o "environment_authored_world': [^,]*" "$WS/tmp/probe_render.log" | tail -1

echo "=== errors (if any) ==="
grep -E 'Error|Traceback|RuntimeError' "$WS/tmp/probe_render.log" | tail -5

echo "=== brightness ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os, glob
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-1001/x1/rgb"
fs = sorted(glob.glob(os.path.join(d, "*")))
print(f"  {len(fs)} rgb files")
for f in fs[:4]:
    im = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
    print(f"  {os.path.basename(f)}: mean={im.mean():.2f} p50={np.percentile(im,50):.1f} "
          f"p95={np.percentile(im,95):.1f} frac_black={(im.max(axis=2)<8).mean():.3f}")
PY
