#!/usr/bin/env bash
# Fix the log document filename (PowerShell/SFTP mangled the UTF-8 name) and
# install the manifests/licenses.
set -uo pipefail
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
UP=/data/raw/huzijian/project1_database/tmp/upstream
LOG=/data/raw/huzijian/project1_database/log
PY=/data/raw/huzijian/project1_database/tools/conda_env/bin/python
cd "$R" || exit 1

TARGET="$LOG/V4.1_调研结果文档_碰撞体生成脚本对OBJ输入的坐标系缺陷_20260923.md"

echo "=== current log dir entries matching V4.1 ==="
ls -la "$LOG" | grep -i 'V4.1' || echo "  (none)"

echo "=== remove mangled variants, then place the correct name ==="
find "$LOG" -maxdepth 1 -name 'V4.1_*' -print -delete
cp -f "$UP/zz_log_doc.md" "$TARGET"
ls -la "$LOG" | grep -i 'V4.1'

echo
echo "=== install elephant manifest + license ==="
cp -f "$UP/elephant_asset.yaml"  assets/objects/special_plush_elephant/asset.yaml
cp -f "$UP/elephant_SOURCE.md"   assets/objects/special_plush_elephant/license/SOURCE.md

echo "=== install replicad manifest + license ==="
cp -f "$UP/replicad_asset.yaml"  assets/environments/replicad_apartment/asset.yaml
cp -f "$UP/replicad_SOURCE.md"   assets/environments/replicad_apartment/license/SOURCE.md

echo
echo "=== maps.yaml: replicad_apartment region cleanliness ==="
"$PY" - <<'PY'
import yaml
m = yaml.safe_load(open("configs/maps.yaml"))
rep = m["maps"]["replicad_apartment"]
n = 0
for grp in rep.get("surface_groups", []):
    print(f"  surface_type={grp.get('surface_type')}")
    for r in grp.get("regions", []):
        n += 1
        print(f"    region_id={r.get('region_id')}")
        print(f"      cleanliness={r.get('cleanliness')!r}")
        print(f"      verification={r.get('verification')!r}")
print(f"  total regions: {n}")
PY

echo
echo "=== final tree: elephant ==="
find assets/objects/special_plush_elephant -printf '%y %10s %p\n' | sort -k3
echo "=== final tree: replicad ==="
find assets/environments/replicad_apartment -printf '%y %10s %p\n' | sort -k3
echo "=== old dir must be gone ==="
ls -d assets/objects/gso_sootheze_cold_therapy_elephant 2>&1 || echo "  old dir absent (good)"
