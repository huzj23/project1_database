#!/usr/bin/env bash
# Run one free_fall smoke sample through the mentor pipeline and surface the
# validation verdict, which is the whole point of his design: reject before render.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

echo "=== config in effect ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import yaml, pathlib
c = yaml.safe_load(open("configs/server.yaml"))
s = yaml.safe_load(open("configs/scenarios/free_fall_gso.yaml"))
print("  render :", c["render"]["samples_per_pixel"], "spp,", c["render"]["device"])
print("  assets :", s["selection"]["asset_ids"])
print("  maps   :", s["selection"]["map_ids"])
print("  frames :", s["timing"]["frame_count"], "@", s["timing"]["video_fps"], "fps")
PY

echo
echo "=== clean previous output (his DatasetWriter uses mkdir(exist_ok=False)) ==="
rm -rf "$REPO/datasets/free_fall/seed-001000/x1"
echo "  removed stale sample dir"

echo
echo "=== run ==="
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x1 > /tmp/ff_smoke.log 2>&1
rc=$?
echo "  exit code: $rc"
echo
grep -E 'SAMPLE_OUTPUT|validation|valid=|reasons|rejected' /tmp/ff_smoke.log | tail -8 | sed 's/^/  /'
echo
echo "=== diagnostics ==="
grep -oE 'RENDER_DIAGNOSTICS=.*' /tmp/ff_smoke.log | tail -1 | tr ',' '\n' | sed 's/^/  /' | head -22
echo
if [ "$rc" -ne 0 ]; then
  echo "=== failure tail ==="
  tail -14 /tmp/ff_smoke.log | sed 's/^/  /'
fi
echo
echo "=== outputs ==="
find datasets -maxdepth 4 -type d 2>/dev/null | head -12 | sed 's/^/  /'
find datasets -name '*.mp4' -o -name 'trajectory.json' -o -name 'collisions.json' 2>/dev/null | head -8 | sed 's/^/  /'
