#!/usr/bin/env bash
# V5.5 stage 03: locate the approved interaction assets' geometry on the server and check
# which mesh-processing libraries the server python has.
#
# The local models/gso tree holds only 8 assets, so the assets themselves may live on the
# server only.  Building colliders needs the real geometry, and it needs to happen where
# the solving happens, so this establishes both facts before the builder runs.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. the four approved assets: is their geometry here? ==="
for a in Borage_GLA240Gamma_Tocopherol Creatine_Monohydrate Big_Dot_Aqua_Pencil_Case Clue_Board_Game_Classic_Edition; do
  echo "  --- $a ---"
  if [ -d "$WS/models/gso/$a" ]; then
    ls -la "$WS/models/gso/$a/" | sed 's/^/      /'
  else
    echo "      DIRECTORY ABSENT"
  fi
done

echo
echo "=== B. how many assets are in models/gso here? ==="
echo "  count: $(ls "$WS/models/gso" 2>/dev/null | wc -l)"
ls "$WS/models/gso" 2>/dev/null | head -20 | sed 's/^/    /'

echo
echo "=== C. server python mesh libraries ==="
for mod in numpy trimesh pybullet scipy; do
  "$PY" - "$mod" <<'PY' 2>&1 | sed 's/^/    /'
import importlib, sys
name = sys.argv[1]
try:
    m = importlib.import_module(name)
    print(f"{name:10s} OK  version={getattr(m, '__version__', 'n/a')}")
except Exception as exc:
    print(f"{name:10s} MISSING ({type(exc).__name__})")
PY
done

echo
echo "=== D. what does the asset registry actually point at? ==="
find "$WS" -maxdepth 4 -name '*.yaml' -path '*asset*' 2>/dev/null | head -10 | sed 's/^/  /'
echo "  --- registry file contents (first registry found) ---"
REG=$(find "$WS" -maxdepth 4 -name 'asset_registry*.yaml' -o -maxdepth 4 -name 'registry*.yaml' 2>/dev/null | head -1)
if [ -n "$REG" ]; then
  echo "  using: $REG"
  head -25 "$REG" | sed 's/^/    /'
else
  echo "  (no registry yaml found at depth <= 4)"
fi

echo
echo "=== E. are the GSO assets perhaps in the vendored/asset root instead? ==="
for d in "$WS/code/physics-video-sim/physics-video-sim-main/assets" \
         "$WS/assets" "$WS/models/kubasic"; do
  echo "  --- $d ---"
  [ -d "$d" ] && ls "$d" | head -8 | sed 's/^/      /' || echo "      (absent)"
done
