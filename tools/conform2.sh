#!/usr/bin/env bash
# ===========================================================================
# Remaining conformance questions before I restructure the assets.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== .gitignore: what is Git-tracked vs HF-synced? ==="
cat .gitignore | sed 's/^/  /'

echo
echo "=== allowed VISUAL extensions (AssetManager) ==="
grep -n 'visual\|\.glb\|\.obj\|\.blend' src/physim/assets/__init__.py | head -25 | sed 's/^/  /'

echo
echo "=== allowed COLLISION mesh/sim extensions ==="
grep -n 'SUPPORTED\|_EXT\|suffix' src/physim/assets/__init__.py | head -20 | sed 's/^/  /'

echo
echo "=== elephant visual dir contents ==="
ls -la assets/objects/gso_sootheze_cold_therapy_elephant/visual/ | sed 's/^/  /'
echo "  --- license/SOURCE.md ---"
cat assets/objects/gso_sootheze_cold_therapy_elephant/license/SOURCE.md | sed 's/^/  /'

echo
echo "=== apartment license/SOURCE.md ==="
cat assets/environments/replicad_apartment/license/SOURCE.md | sed 's/^/  /'

echo
echo "=== mentor repo docs/ (more guidance?) ==="
ls docs/ | sed 's/^/  /'

echo
echo "=== does the mentor repo track source/ or is it gitignored? ==="
git check-ignore -v assets/objects/food_lime/source 2>/dev/null | sed 's/^/  /' || echo "  not ignored by a rule (or no git)"

echo
echo "=== category values currently used by ALL our assets ==="
grep -h '^category:' assets/objects/*/asset.yaml assets/environments/*/asset.yaml 2>/dev/null | sort | uniq -c | sed 's/^/  /'

echo
echo "=== mentor's own categories for comparison ==="
grep -h '^category:' "$WS/tmp/upstream_x/physics-video-sim-main"/assets/objects/*/asset.yaml 2>/dev/null | sort | uniq -c | sed 's/^/  /'
