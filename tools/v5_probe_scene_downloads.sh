#!/usr/bin/env bash
set -euo pipefail

export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"

/usr/bin/printf '%s\n' '--- EXISTING LARGE SCENE-LIKE FILES IN WORKSPACE ---'
/data/raw/huzijian/project1_database/tools/conda_env/bin/python - <<'PY'
from pathlib import Path

root = Path("/data/raw/huzijian/project1_database")
suffixes = {".blend", ".glb", ".gltf", ".zip", ".tar", ".gz", ".7z"}
skip = {"outcomes", ".git", "tools", "code"}
for path in root.rglob("*"):
    try:
        relative = path.relative_to(root)
    except ValueError:
        continue
    if any(part in skip for part in relative.parts):
        continue
    if path.is_file() and path.suffix.lower() in suffixes and path.stat().st_size >= 5 * 1024 * 1024:
        print(f"{path.stat().st_size}\t{path}")
PY

/usr/bin/printf '%s\n' '--- OFFICIAL DOWNLOAD HEADERS ---'
for url in \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/the_shed.zip' \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/hidden_alley.zip' \
  'https://dl.polyhaven.org/file/ph-assets/Scenes/pine_forest.zip' \
  'https://download.blender.org/demo/cycles/flat-archiviz.blend'
do
  /usr/bin/printf 'URL %s\n' "$url"
  /usr/bin/curl --location --silent --show-error --head "$url" \
    | /usr/bin/grep -iE '^(HTTP/|content-length:|content-type:|last-modified:|etag:)'
done
