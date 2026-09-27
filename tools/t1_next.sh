#!/usr/bin/env bash
# Depth file naming + T1 runner progress.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== depth dir listing ==="
ls "$REPO/datasets/rolling/seed-001001/x1/depth" 2>/dev/null | head -5 | sed 's/^/  /'
echo "  count: $(ls "$REPO/datasets/rolling/seed-001001/x1/depth" 2>/dev/null | wc -l)"

echo
echo "=== depth stats (any extension) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob
import numpy as np
from PIL import Image
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-001001/x1/depth"
fs = sorted(glob.glob(d + "/*"))
print("  files:", [f.split("/")[-1] for f in fs[:4]])
for f in fs[:3]:
    try:
        a = np.asarray(Image.open(f))
        print(f"  {f.split('/')[-1]}: shape={a.shape} dtype={a.dtype} min={a.min()} max={a.max()} unique={len(np.unique(a))}")
    except Exception as e:
        print(f"  {f.split('/')[-1]}: {type(e).__name__}: {e}")
PY

echo
echo "=== T1 runner stdout (all clips so far) ==="
cat "$WS/tmp/t1_render_stdout.log" 2>/dev/null | tr -d '\r'

echo
echo "=== which clips exist ==="
ls -d "$REPO"/datasets/*/seed-*/x1 2>/dev/null | while read d; do
  n=$(ls "$d/rgb" 2>/dev/null | wc -l)
  v=$(ls "$d"/*.mp4 2>/dev/null | head -1)
  echo "  $d rgb=$n video=$([ -n "$v" ] && echo yes || echo no)"
done

echo
echo "=== currently running ==="
pgrep -af "generate.py" | head -2 | sed 's/^/  /'
