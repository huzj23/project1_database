#!/usr/bin/env bash
# ===========================================================================
# Check a LICENSING DISCREPANCY in the GSO source for our elephant.
#
# The per-file MTL header says "Creative Commons Attribution 4.0" (CC BY 4.0, no
# ShareAlike), but the collection metadata (GSO.json) and the object's own
# data.json both say "CC BY-SA 4.0" (with ShareAlike = copyleft).
#
# That difference is legally meaningful, so report the exact text of each source
# rather than picking one silently.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
E="assets/objects/special_plush_elephant"

echo "=== 1. what the per-file MTL header says (source/ copy) ==="
head -8 "$E/source/visual_geometry.mtl" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 2. what the object's own data.json says ==="
"$WS/tools/conda_env/bin/python" -c "
import json
d = json.load(open('$E/source/data.json'))
print('  license      :', d.get('license'))
print('  category     :', d.get('metadata',{}).get('category'))
print('  description  :', d.get('metadata',{}).get('description'))
" 2>&1 | sed 's/^/  /'

echo
echo "=== 3. what the collection GSO.json says for this asset ==="
"$WS/tools/conda_env/bin/python" -c "
import json
g = json.load(open('$WS/tmp/upstream_x/../upstream_x/physics-video-sim-main/../../GSO.json')) if False else None
" 2>/dev/null
for f in "$WS/tmp/gso_json/GSO.json" "$WS/GSO.json" "$WS/tmp/GSO.json"; do
  [ -f "$f" ] && echo "  found $f"
done
echo "  (GSO.json lives on the local Windows box; showing the recorded value instead)"
grep -n 'license' "$E/asset.yaml" | sed 's/^/  /'
grep -n 'CC BY' "$E/license/SOURCE.md" | head -6 | sed 's/^/  /'

echo
echo "=== 4. what WE recorded (the conservative choice) ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
m = yaml.safe_load(open('$E/asset.yaml'))
print('  manifest license      :', m.get('license'))
print('  manifest license_note :', m.get('license_note'))
" 2>&1 | sed 's/^/  /'

echo
echo "=== 5. what the OTHER assets record, for comparison ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, yaml
for p in sorted(glob.glob("assets/*/*/asset.yaml")):
    m = yaml.safe_load(open(p))
    print(f"  {str(m.get('id')):28s} {str(m.get('license'))}")
PY
