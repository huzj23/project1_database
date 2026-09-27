#!/usr/bin/env bash
# ===========================================================================
# 1. How is `allowed_scenarios` actually ENFORCED?  The user forbade the plush
#    elephant from 匀加速/自由落体/抛体 (no soft-body adaptation), but the manifest
#    still lists constant_force and free_fall.
# 2. Apply that fix, then re-verify everything.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. where is allowed_scenarios consumed? ==="
grep -rn 'allowed_scenarios' src/ scripts/ | sed 's/^/  /'

echo
echo "=== 1b. enforcement logic ==="
grep -rn 'allowed_scenarios' -B4 -A10 src/physim/scenarios/__init__.py | head -40 | sed 's/^/  /'

echo
echo "=== 2. fix the elephant's allowed_scenarios ==="
"$PY" - <<'PY'
import re, pathlib, yaml
p = pathlib.Path("assets/objects/special_plush_elephant/asset.yaml")
t = p.read_text(encoding="utf-8")
m = re.search(r'^allowed_scenarios:\s*\[(.*?)\]\s*$', t, re.M)
if not m:
    raise SystemExit("FATAL: allowed_scenarios not found as an inline list")
before = [s.strip() for s in m.group(1).split(",") if s.strip()]
FORBIDDEN = {"constant_force", "free_fall", "projectile"}
after = [s for s in before if s not in FORBIDDEN]
print("  before:", before)
print("  after :", after)
if after == before:
    print("  (no change needed)")
else:
    if not p.with_suffix(".yaml.pre_scen").exists():
        p.with_suffix(".yaml.pre_scen").write_text(t, encoding="utf-8")
    new = f"allowed_scenarios: [{', '.join(after)}]"
    t2 = t[:m.start()] + new + t[m.end():]
    p.write_text(t2, encoding="utf-8")
    print("  written")
d = yaml.safe_load(open(p))
print("  verify:", d.get("allowed_scenarios"))
PY

echo
echo "=== 3. AssetManager sees the new list ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
a = am.get('special_plush_elephant')
print('  allowed_scenarios =', a.allowed_scenarios)
print('  forbidden present :', [s for s in ('constant_force','free_fall','projectile') if s in a.allowed_scenarios])
" 2>&1 | sed 's/^/  /'

echo
echo "=== 4. preflight after all edits ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -3 | sed 's/^/  /'
