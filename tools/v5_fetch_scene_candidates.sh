#!/usr/bin/env bash
set -euo pipefail

source /data/raw/huzijian/project1_database/tools/server_env.sh
export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"

/data/raw/huzijian/project1_database/tools/conda_env/bin/python - <<'PY'
import shutil
from pathlib import Path

workspace = Path("/data/raw/huzijian/project1_database")
usage = shutil.disk_usage(workspace)
print(f"DISK total={usage.total} used={usage.used} free={usage.free}", flush=True)
if usage.free < 9 * 1024**3:
    raise SystemExit("less than 9 GiB free; refusing scene downloads")
PY

/usr/bin/mkdir -p \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/the_shed/source \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/hidden_alley/source \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/pine_forest/source \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/italian_flat/source

/usr/bin/wget --continue --progress=dot:giga \
  --output-document=/data/raw/huzijian/project1_database/models/backgrounds/candidates/the_shed/source/the_shed.zip \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/the_shed.zip' &
pid_shed=$!

/usr/bin/wget --continue --progress=dot:giga \
  --output-document=/data/raw/huzijian/project1_database/models/backgrounds/candidates/hidden_alley/source/hidden_alley.zip \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/hidden_alley.zip' &
pid_alley=$!

/usr/bin/wget --continue --progress=dot:giga \
  --output-document=/data/raw/huzijian/project1_database/models/backgrounds/candidates/pine_forest/source/pine_forest.zip \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/pine_forest.zip' &
pid_pine=$!

/usr/bin/wget --continue --progress=dot:giga \
  --user-agent='Mozilla/5.0' \
  --referer='https://www.blender.org/download/demo-files/' \
  --output-document=/data/raw/huzijian/project1_database/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend \
  'https://download.blender.org/demo/cycles/flat-archiviz.blend' &
pid_flat=$!

status=0
wait "$pid_shed" || status=1
wait "$pid_alley" || status=1
wait "$pid_pine" || status=1
wait "$pid_flat" || status=1

/usr/bin/sha256sum \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/the_shed/source/the_shed.zip \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/hidden_alley/source/hidden_alley.zip \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/pine_forest/source/pine_forest.zip \
  /data/raw/huzijian/project1_database/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend || true

/usr/bin/printf 'SCENE_DOWNLOAD_STATUS=%s\n' "$status"
exit "$status"
