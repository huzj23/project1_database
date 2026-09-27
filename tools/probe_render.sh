#!/usr/bin/env bash
# ===========================================================================
# Verify the lighting fix BEFORE committing 3 hours of rendering.
#
# With the 7 authored POINT lights now found, the render will be lit only by the
# scene author (iron rule 4).  The authored world is BLACK (0,0,0) at strength 1.0,
# so if the authored lights are weak the image could come out nearly black.
#
# Launch one sample, wait for the first frames, and measure brightness.  If the
# image is reasonable the run continues on its own.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

sed -i 's|^  scenario_config: .*|  scenario_config: configs/scenarios/rolling_gso.yaml|' configs/server.yaml
rm -rf datasets/rolling/seed-1001

tmux kill-session -t t1probe 2>/dev/null
tmux new-session -d -s t1probe "cd $REPO && $WS/tools/conda_env/bin/python scripts/generate.py --config configs/server.yaml --seed 1001 --variant x1 --asset-id gso_whey_protein_vanilla > $WS/tmp/probe_render.log 2>&1"
echo "launched probe render; waiting for first frames..."
for i in $(seq 1 40); do
  sleep 15
  n=$(ls datasets/rolling/seed-1001/x1/rgb 2>/dev/null | wc -l)
  echo "  t=$((i*15))s rgb_frames=$n"
  if [ "$n" -ge 3 ]; then break; fi
done

echo
echo "=== lighting diagnostics from the new render ==="
grep -o "environment_lighting_source': '[a-z_+]*'" "$WS/tmp/probe_render.log" | tail -1 | sed 's/^/  /'
grep -o "environment_light_count': [0-9]*" "$WS/tmp/probe_render.log" | tail -1 | sed 's/^/  /'
grep -o "environment_light_types': \[[^]]*\]" "$WS/tmp/probe_render.log" | tail -1 | sed 's/^/  /'
grep -o "environment_authored_world': [^,]*" "$WS/tmp/probe_render.log" | tail -1 | sed 's/^/  /'

echo
echo "=== brightness of the first rendered frames ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import os, glob
import numpy as np
try:
    from PIL import Image
except ImportError:
    print("  PIL missing"); raise SystemExit
d = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/rolling/seed-1001/x1/rgb"
fs = sorted(glob.glob(os.path.join(d, "*")))
print(f"  {len(fs)} rgb files")
for f in fs[:4]:
    im = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
    print(f"  {os.path.basename(f)}: shape={im.shape} mean={im.mean():.2f} "
          f"p05={np.percentile(im,5):.1f} p50={np.percentile(im,50):.1f} "
          f"p95={np.percentile(im,95):.1f} max={im.max():.0f} "
          f"frac_black={(im.max(axis=2)<8).mean():.3f}")
PY
