#!/usr/bin/env bash
# V5.5 stage 03: investigate the two source .blend hash mismatches.
#
# 03 section 1: "如果哈希不符，先确认是原文件、打包文件还是运行副本，保留两者并说明
# 差异；不要覆盖或假定损坏。"
#
# READ-ONLY. Nothing is deleted or overwritten.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

for SCENE in hidden_alley the_shed; do
  echo "=================================================================="
  echo "=== $SCENE ==="
  echo "=================================================================="
  D="$WS/models/backgrounds/candidates/$SCENE"
  echo "--- full tree (depth 4) ---"
  find "$D" -maxdepth 4 -printf '%y %10s  %TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null \
    | sort -k4 | head -40 | sed 's/^/  /'

  echo
  echo "--- any archive files (zip/7z/tar/gz) ---"
  find "$D" -type f \( -name '*.zip' -o -name '*.7z' -o -name '*.tar*' -o -name '*.gz' -o -name '*.xz' -o -name '*.rar' \) \
    -printf '  %10s  %p\n' 2>/dev/null || echo "  (none)"

  echo
  echo "--- any partially-written / temp / backup blends ---"
  find "$D" -type f \( -name '*.blend1' -o -name '*.blend2' -o -name '*.part' -o -name '*.tmp' -o -name '*.crdownload' -o -name '*.blend?' \) \
    -printf '  %10s  %p\n' 2>/dev/null || echo "  (none)"

  echo
  echo "--- ALL .blend files here with hashes ---"
  find "$D" -name '*.blend' -type f 2>/dev/null | while IFS= read -r f; do
    printf '  %10s  %s\n             sha256=%s\n' "$(stat -c%s "$f")" "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
  done

  echo
done

echo "=================================================================="
echo "=== is an extraction still RUNNING right now? ==="
echo "=================================================================="
ps -eo pid,etimes,cmd 2>/dev/null | grep -Ei '7z|unzip|blender|extract' | grep -v grep | head -10 | sed 's/^/  /' || echo "  (no extraction process)"
echo "  --- our own tmux sessions ---"
tmux -S "$WS/tmp/tmux_v55.sock" ls 2>&1 | sed 's/^/  /'
