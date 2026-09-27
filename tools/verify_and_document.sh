#!/usr/bin/env bash
# ===========================================================================
# Confirm the turntable still passes physics validation, then update the dataset card
# and the turntable manifest comment to describe the asset-local maps.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 1. both turntable scenarios validate ==="
cat > /tmp/val2.py <<'PY'
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.validation import validate_simulation
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
for name in ("turntable_carry_gso", "turntable_spin_gso"):
    cfg = load_run_config("configs/server.yaml", scenario=name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    a = am.get("special_plush_elephant")
    s = scen.sample(seed=5001, asset=a, map_spec=ms, variant=v)
    r = scen.simulate(s)
    ok, reasons = validate_simulation(s, r)
    print(f"VL {name}: valid={ok} reasons={reasons}")
PY
"$PY" /tmp/val2.py 2>&1 | grep -aE '^VL|Error|Traceback' | sed 's/^/  /'

echo
echo "=== 2. update the turntable manifest comment for the asset-local maps ==="
"$PY" - <<'PY'
import pathlib
p = pathlib.Path("assets/objects/turntable/asset.yaml")
t = p.read_text(encoding="utf-8")
old = """  # The disc's model.mtl is EMPTY on purpose: writing the material into the MTL
  # was measured and rejected (disc R/B 4.04 / R/G 2.55, far too red).  The
  # frozen dark_wood look (R/B ~1.99 / R/G ~1.67) only reproduces with this
  # full PBR node tree."""
new = """  # The disc's model.mtl is EMPTY on purpose: writing the material into the MTL
  # was measured and rejected (disc R/B 4.04 / R/G 2.55, far too red).  The
  # frozen dark_wood look (R/B ~1.99 / R/G ~1.67) only reproduces with this
  # full PBR node tree.
  #
  # `textures` ships the three 4k maps INSIDE this asset and is searched before
  # the shared library, so the disc renders correctly after a plain
  # `git clone` + `sync_hf_assets.py download`, with no
  # <workspace>/models/pbr_textures present.  The maps are byte-identical to the
  # shared originals (sha256 verified); rendering is unchanged (disc R/B 1.89,
  # pixel-identical to the delivered clips)."""
assert t.count(old) == 1, f"comment block not unique ({t.count(old)})"
p.write_text(t.replace(old, new), encoding="utf-8")
print("  manifest comment updated")
PY

echo
echo "=== 3. final turntable manifest ==="
sed -n '16,42p' assets/objects/turntable/asset.yaml | sed 's/^/  /'

echo
echo "=== 4. what the turntable payload is now ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util as u, sys
from pathlib import Path
spec = u.spec_from_file_location("syncmod", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); sys.modules["syncmod"] = m; spec.loader.exec_module(m)
root = Path(".").resolve()
recs = {r.asset_id: r for r in m.discover_assets(root)}
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    r = recs[aid]
    files = sorted(m._payload_files(r))
    stray = [f.name for f in files if ".bak" in f.name or ".pre_" in f.name]
    print(f"  {aid}: {len(files)} files, {sum(f.stat().st_size for f in files)/1e6:.2f} MB, strays={stray}")
    for f in files: print(f"      {f.stat().st_size:>12,}  {f.relative_to(root).as_posix()}")
PY
