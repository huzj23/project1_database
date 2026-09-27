#!/usr/bin/env bash
# ===========================================================================
# Two checks that decide the remaining edits:
#
#  A. The user said: "毛绒象不要参与匀加速 自由落体 和 抛体" -- but the elephant's
#     allowed_scenarios currently INCLUDES constant_force and free_fall.  Find every
#     live config that would let the elephant run those scenarios.
#  B. Is visual/textures/dark_wood_diff_1k.jpg referenced by anything, or dead weight?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== A. elephant in constant_force / free_fall / projectile configs? ==="
for s in constant_force free_fall projectile damping rolling; do
  for f in configs/scenarios/${s}_gso.yaml configs/scenarios/${s}.yaml; do
    [ -f "$f" ] || continue
    if grep -q 'special_plush_elephant\|gso_sootheze' "$f"; then
      echo "  *** $f MENTIONS the elephant:"
      grep -n 'special_plush_elephant\|gso_sootheze\|asset_ids' -A6 "$f" | head -14 | sed 's/^/      /'
    else
      echo "  ok  $f  (no elephant)"
    fi
  done
done

echo
echo "=== A2. every live scenario config and its asset_ids ==="
for f in configs/scenarios/*.yaml; do
  case "$f" in *.pre_*|*pre_camC*|*pre_pullback*|*pre_eleph*) continue;; esac
  echo "  --- $f"
  "$PY" -c "
import yaml
d=yaml.safe_load(open('$f')) or {}
ids=(d.get('project') or {}).get('asset_ids') or d.get('asset_ids')
print('      scenario=', (d.get('project') or {}).get('scenario_config') or d.get('scenario'))
print('      asset_ids=', ids)
" 2>&1 | sed 's/^/  /'
done

echo
echo "=== B. who references dark_wood_diff_1k? ==="
grep -rn 'dark_wood_diff_1k' --include='*.py' --include='*.yaml' --include='*.mtl' --include='*.md' . 2>/dev/null | grep -v '^./datasets' | sed 's/^/  /' || echo "  nothing references it"

echo
echo "=== B2. turntable visual/textures contents + mtl content ==="
ls -la assets/objects/turntable/visual/textures/ | sed 's/^/  /'
echo "  model.mtl (all $(( $(wc -l < assets/objects/turntable/visual/model.mtl) )) lines):"
cat assets/objects/turntable/visual/model.mtl | sed 's/^/    | /'
echo "  model.mtl.nomtl-bak:"
cat assets/objects/turntable/visual/model.mtl.nomtl-bak | sed 's/^/    | /'
