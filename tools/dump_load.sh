#!/usr/bin/env bash
# ===========================================================================
# Dump the _load() region so the MaterialSpec patch uses the right variable names.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== assets/__init__.py: from 'visual =' to the AssetSpec return ==="
grep -n 'def _load\|visual = \|asset_dir\|material=self._material' src/physim/assets/__init__.py | sed 's/^/  /'

echo
echo "=== lines 290-340 ==="
sed -n '290,340p' src/physim/assets/__init__.py | cat -n | sed 's/^/  /'

echo
echo "=== the exact AssetSpec return block ==="
sed -n '/material=self._material/,+3p' src/physim/assets/__init__.py | sed 's/^/  /'
echo "  --- and 12 lines before it ---"
grep -n 'material=self._material' src/physim/assets/__init__.py | cut -d: -f1 | while read n; do
  sed -n "$((n-14)),$((n+2))p" src/physim/assets/__init__.py | cat -n | sed 's/^/  /'
done
