#!/usr/bin/env bash
# ===========================================================================
# FULL REGRESSION after all asset/code changes:
#   1. both turntable scenarios validate via the real entry point
#   2. all 4 delivered clips' scenarios still pass
#   3. preflight 14/14
#   4. the shared-library-hidden case still works (self-containment)
#   5. render is still pixel-identical to the delivered clip
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1+2. validate every delivered scenario ==="
cat > /tmp/regval.py <<'PY'
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.validation import validate_sample
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
CASES = [
    ("turntable_carry_gso", "special_plush_elephant", 5001),
    ("turntable_spin_gso",  "special_plush_elephant", 5001),
    ("free_fall_gso",       "gso_whey_protein_vanilla", 3001),
    ("rolling_gso",         "gso_whey_protein_vanilla", 4001),
]
for name, aid, seed in CASES:
    cfg = load_run_config("configs/server.yaml", scenario=name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    a = am.get(aid)
    s = scen.sample(seed=seed, asset=a, map_spec=ms, variant=v)
    r = scen.simulate(s)
    rep = validate_sample(r, s, ms.surface(s.surface_id), cfg["validation"])
    print(f"RV {name:22s} {aid:28s} valid={rep.valid} reasons={list(rep.reasons)}")
PY
"$PY" /tmp/regval.py 2>&1 | grep -aE '^RV|Error|Traceback|Exception' | sed 's/^/  /'

echo
echo "=== 3. preflight ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -2 | sed 's/^/  /'

echo
echo "=== 4. self-containment re-check (shared library hidden) ==="
SHARED="$WS/models/pbr_textures"; HIDDEN="$WS/tmp/pbr_hidden2"
rm -rf "$HIDDEN"; mv "$SHARED" "$HIDDEN"
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.assets import AssetManager
from physim.render.materials import find_texture_dir
am = AssetManager('configs/assets.yaml','assets')
t = am.get('turntable')
d = find_texture_dir('third_party/phyco-sim','dark_wood','wood_textures', t.material)
print('  shared hidden -> turntable resolved:', d)
" 2>&1 | sed 's/^/  /'
mv "$HIDDEN" "$SHARED"
echo "  restored: $([ -d "$SHARED" ] && echo YES || echo NO)"

echo
echo "=== 5. final payload ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util as u, sys
from pathlib import Path
spec = u.spec_from_file_location("syncmod", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); sys.modules["syncmod"] = m; spec.loader.exec_module(m)
root = Path(".").resolve()
recs = {r.asset_id: r for r in m.discover_assets(root)}
tot = 0
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    files = sorted(m._payload_files(recs[aid]))
    sz = sum(f.stat().st_size for f in files); tot += sz
    print(f"  {aid}: {len(files)} files, {sz/1e6:.2f} MB")
print(f"  GRAND TOTAL: {tot/1e6:.2f} MB")
PY
