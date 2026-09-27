#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# P0: stand up the mentor's physics-video-sim skeleton on the server, reusing
# OUR vendored phyco-sim (which already contains the Kubric fork) as
# third_party/phyco-sim.
#
# We reuse his CODE STRUCTURE only.  Objects and environments stay ours, per the
# agreed plan, so the missing visual assets in his zip are not a blocker.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

REPO="$WS/code/physics-video-sim"
SRC="$REPO/physics-video-sim-main"
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. 目录布局 ==="
mkdir -p "$REPO"
ls -d "$SRC" >/dev/null 2>&1 && echo "  repo present: $SRC" || { echo "  MISSING repo -- upload first"; exit 1; }

echo
echo "=== 2. third_party 接线 ==="
# our vendored phyco-sim already bundles the kubric fork it needs
if [ ! -e "$SRC/third_party/phyco-sim/kubric" ]; then
  rm -rf "$SRC/third_party/phyco-sim"
  ln -s "$WS/code/vendor/phyco-sim" "$SRC/third_party/phyco-sim"
  echo "  linked third_party/phyco-sim -> $WS/code/vendor/phyco-sim"
else
  echo "  third_party/phyco-sim already wired"
fi
ls -la "$SRC/third_party/" | sed 's/^/    /'

echo
echo "=== 3. 安装（editable，无网络依赖）==="
cd "$SRC" || exit 1
# numpy 1.26.4 and PyYAML only; avoid pip reaching the network for anything else
"$PY" -m pip install --no-deps -e . 2>&1 | tail -3 | sed 's/^/    /'
"$PY" -c "import yaml, numpy; print('    yaml', yaml.__version__, ' numpy', numpy.__version__)"

echo
echo "=== 4. 依赖自检 ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/    /'
import sys
sys.path.insert(0, "src")
try:
    import physim
    print("physim import OK:", physim.__file__)
except Exception as e:
    print(f"physim import FAILED: {type(e).__name__}: {e}")
PY

echo
echo "=== 5. 配置：指向我们的 phyco-sim 与 Blender ==="
cat > "$SRC/configs/server.yaml" <<YAML
profile: server

project:
  scenario_config: configs/scenarios/free_fall.yaml
  seed: 123

paths:
  asset_registry: configs/assets.yaml
  map_registry: configs/maps.yaml
  asset_root: assets
  output_root: datasets
  cache_root: cache
  log_root: logs
  blender_executable: $WS/tools/runtime/blender-3.4.1-linux-x64/blender
  phyco_sim_root: third_party/phyco-sim

execution:
  headless: true
  num_workers: 1
  num_samples: 1
  gpu_ids: []

render:
  engine: CYCLES
  device: CPU
  compute_backend: NONE
  samples_per_pixel: 32
  use_denoising: true
  use_adaptive_sampling: true
  adaptive_threshold: 0.01
  max_bounces: 8
  view_transform: Filmic
  look: Medium High Contrast
  exposure: 0.0
  gamma: 1.0
  save_blend: false
YAML
echo "  wrote configs/server.yaml (CPU render; GPU+depth is unsafe here)"

echo
echo "=== 6. 单元测试 ==="
"$PY" -m pytest -q 2>&1 | tail -12 | sed 's/^/    /'
