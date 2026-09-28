#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01 section 6: inventory SERVER-side code and small assets.
#
# Produces, inside this run's own directory:
#   server_inventory.txt          <size>\t<sha256>\t<absolute path>
#   server_asset_inventory.txt    <sha256>\t<absolute path>
#   server_tools_inventory.txt    <size>\t<sha256>\t<absolute path>
#
# READ-ONLY with respect to existing content: nothing is deleted or overwritten.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

RUN_ID="${RUN_ID:-$(date +%Y%m%dT%H%M%S)}"
OUT="$WS/outcomes/v55/bootstrap/$RUN_ID"
mkdir -p "$OUT"
echo "RUN_ID = $RUN_ID"
echo "OUT    = $OUT"

# Emit "<size>\t<sha256>\t<path>" for every path read from stdin.
emit_sized() {
  local path
  while IFS= read -r path; do
    [ -f "$path" ] || continue
    printf '%s\t%s\t%s\n' "$(stat -c%s "$path")" "$(sha256sum "$path" | cut -d' ' -f1)" "$path"
  done
}

echo
echo "=== A. code/ python + config inventory ==="
find "$WS/code" -type f \
  \( -name '*.py' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' -o -name '*.md' -o -name '*.sh' -o -name '*.txt' \) \
  -not -path '*/__pycache__/*' -not -path '*/.git/*' -not -path '*/third_party/*' \
  2>/dev/null | LC_ALL=C sort | emit_sized > "$OUT/server_inventory.txt"
echo "  files: $(wc -l < "$OUT/server_inventory.txt")"

echo
echo "=== B. project-side asset manifests + collision meshes ==="
find "$WS/code/physics-video-sim/physics-video-sim-main/assets" -type f \
  \( -path '*/collision/*' -o -name 'asset.yaml' -o -name '*.json' -o -name '*.urdf' -o -name '*.mtl' \) \
  -not -path '*/__pycache__/*' 2>/dev/null | LC_ALL=C sort | emit_sized \
  > "$OUT/server_asset_inventory.txt"
echo "  files: $(wc -l < "$OUT/server_asset_inventory.txt")"

echo
echo "=== C. workspace-level tools/ scripts ==="
find "$WS/tools" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) \
  2>/dev/null | LC_ALL=C sort | emit_sized > "$OUT/server_tools_inventory.txt"
echo "  files: $(wc -l < "$OUT/server_tools_inventory.txt")"

echo
echo "=== D. disk by area ==="
for d in code outcomes tmp remove; do
  printf '  %-10s %s\n' "$d" "$(du -sh "$WS/$d" 2>/dev/null | cut -f1)"
done

echo
echo "=== E. configs/scenarios listing (V5.5 will extend these) ==="
ls "$WS/code/physics-video-sim/physics-video-sim-main/configs/scenarios/" 2>/dev/null | sed 's/^/  /'

echo
echo "=== F. outputs ==="
ls -la "$OUT" | sed 's/^/  /'
