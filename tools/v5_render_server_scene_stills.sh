#!/usr/bin/env bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"
export OMP_NUM_THREADS="8"
export OPENBLAS_NUM_THREADS="8"
export MKL_NUM_THREADS="8"

BLENDER='/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender'
SCRIPT='/data/raw/huzijian/project1_database/tools/v5_render_scene_still.py'
OUT='/data/raw/huzijian/project1_database/outcomes/v5_asset_review/scenes'
LOG='/data/raw/huzijian/project1_database/tmp/v5_scene_render_logs'
/usr/bin/mkdir -p "$OUT" "$LOG"

"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend' \
  --threads 8 --python "$SCRIPT" -- \
  --tag the_shed --camera Still_01 --samples 64 \
  --output "$OUT/the_shed.png" --report "$OUT/the_shed.json" \
  > "$LOG/the_shed.log" 2>&1 &
pid_shed=$!

"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/pine_forest/extracted/polyhaven_pine_fir_forest.blend' \
  --threads 8 --python "$SCRIPT" -- \
  --tag pine_forest --camera Camera1 --samples 64 \
  --output "$OUT/pine_forest.png" --report "$OUT/pine_forest.json" \
  > "$LOG/pine_forest.log" 2>&1 &
pid_pine=$!

"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend' \
  --threads 8 --python "$SCRIPT" -- \
  --tag italian_flat --camera 'Cam Living' --samples 64 \
  --output "$OUT/italian_flat.png" --report "$OUT/italian_flat.json" \
  > "$LOG/italian_flat.log" 2>&1 &
pid_flat=$!

status=0
wait "$pid_shed" || status=1
wait "$pid_pine" || status=1
wait "$pid_flat" || status=1
/usr/bin/printf 'SERVER_SCENE_RENDER_STATUS=%s\n' "$status"
exit "$status"
