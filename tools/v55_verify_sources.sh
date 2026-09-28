#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 03 section 1: locate and verify the three source .blend scenes against
# the SHA-256 baselines the plan declares.
#
# 03: "如果哈希不符，先确认是原文件、打包文件还是运行副本，保留两者并说明差异；
#      不要覆盖或假定损坏。"
#
# READ-ONLY. Nothing is deleted or overwritten.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

OUT="$WS/outcomes/v55/bootstrap/20260928T194500"
mkdir -p "$OUT"

echo "=== A. where do the candidate background scenes live? ==="
for base in "$WS/models/backgrounds" "$WS/models" "$WS/code/scenarios"; do
  echo "  --- $base ---"
  if [ -d "$base" ]; then
    find "$base" -maxdepth 4 -type d 2>/dev/null | head -25 | sed 's/^/    /'
  else
    echo "    (missing)"
  fi
done

echo
echo "=== B. every .blend under models/backgrounds (path, size, mtime) ==="
find "$WS/models/backgrounds" -name '*.blend' -type f 2>/dev/null \
  -printf '%10s  %TY-%Tm-%Td  %p\n' | sort -k3 | sed 's/^/  /'

echo
echo "=== C. hash the three planned sources against the baselines ==="
check_one() {
  local label="$1" want="$2"; shift 2
  echo "  --- $label (planned sha256 $want) ---"
  local found=0
  for path in "$@"; do
    if [ -f "$path" ]; then
      found=1
      local got size
      got=$(sha256sum "$path" | cut -d' ' -f1)
      size=$(stat -c%s "$path")
      if [ "$got" = "$want" ]; then
        echo "    MATCH    $path"
      else
        echo "    MISMATCH $path"
        echo "             got=$got"
      fi
      echo "             size=$size"
    else
      echo "    ABSENT   $path"
    fi
  done
  [ "$found" = 0 ] && echo "    (no candidate path existed)"
}

check_one "Italian Flat" \
  "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25" \
  "$WS/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"

check_one "Hidden Alley" \
  "3dd51c6dc7aad321e6cd4bada26785d87cdf376e649f20aa4f87ef5cf127e151" \
  "$WS/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"

check_one "The Shed" \
  "18b007e0f55c4bb3b5f746c698b6c524508253cb763f2b7b14345cbefb81c8d0" \
  "$WS/models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend"

echo
echo "=== D. brute-force: hash EVERY .blend and report which baseline it matches ==="
declare -A BASE
BASE[0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25]="Italian Flat"
BASE[3dd51c6dc7aad321e6cd4bada26785d87cdf376e649f20aa4f87ef5cf127e151]="Hidden Alley"
BASE[18b007e0f55c4bb3b5f746c698b6c524508253cb763f2b7b14345cbefb81c8d0]="The Shed"

find "$WS/models" -name '*.blend' -type f 2>/dev/null | while IFS= read -r f; do
  h=$(sha256sum "$f" | cut -d' ' -f1)
  tag="${BASE[$h]:-}"
  if [ -n "$tag" ]; then
    echo "  MATCHES $tag -> $f"
  fi
done

echo
echo "=== E. candidate objects (asset review outputs) ==="
ls "$WS/outcomes/v5_asset_review" 2>/dev/null | sed 's/^/  /' || echo "  (missing)"
echo "  --- objects dir ---"
ls "$WS/outcomes/v5_asset_review/objects" 2>/dev/null | head -20 | sed 's/^/    /' || true

echo
echo "=== F. GSO models present on the server ==="
ls "$WS/models/gso" 2>/dev/null | head -30 | sed 's/^/  /' || echo "  (missing)"
echo "  count: $(ls "$WS/models/gso" 2>/dev/null | wc -l)"

echo
echo "=== G. candidate inventory json ==="
for f in "$WS/tmp/v5_candidate_inventory.json" "$WS/models/v5_candidate_inventory.json"; do
  [ -f "$f" ] && echo "  present: $f ($(stat -c%s "$f") bytes)" || echo "  absent : $f"
done
