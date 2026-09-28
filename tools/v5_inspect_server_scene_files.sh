#!/usr/bin/env bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"
export OMP_NUM_THREADS="8"
export OPENBLAS_NUM_THREADS="8"
export MKL_NUM_THREADS="8"

BLENDER='/data/raw/huzijian/project1_database/tools/runtime/blender-3.4.1-linux-x64/blender'
SCRIPT='/data/raw/huzijian/project1_database/tools/v5_inspect_scene_file.py'
REPORT_ROOT='/data/raw/huzijian/project1_database/outcomes/v5_asset_review/scenes/audits'
/usr/bin/mkdir -p "$REPORT_ROOT"

"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend' \
  --threads 8 --python "$SCRIPT" -- --tag the_shed --report "$REPORT_ROOT/the_shed.json"
"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/pine_forest/extracted/polyhaven_pine_fir_forest.blend' \
  --threads 8 --python "$SCRIPT" -- --tag pine_forest --report "$REPORT_ROOT/pine_forest.json"
"$BLENDER" --background '/data/raw/huzijian/project1_database/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend' \
  --threads 8 --python "$SCRIPT" -- --tag italian_flat --report "$REPORT_ROOT/italian_flat.json"

/usr/bin/printf '%s\n' 'SERVER_SCENE_FILE_AUDITS_DONE; hidden_alley requires local Blender 4.2'
