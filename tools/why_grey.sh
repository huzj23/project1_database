#!/usr/bin/env bash
# ===========================================================================
# Why did MY still harness render a GREY disc (R/B 1.03) when the delivered clips
# from generate.py are wood (R/B 1.89)?
#
# The renderer builds the disc only when
#     simulation.support_trajectory and sample.support_visual_path
# and then sets
#     support_object.render_material = getattr(sample, "support_material", None)
#
# So if support_visual_path is set but support_material is None, the disc renders
# grey.  Compare what scen.sample() returns against what generate.py's
# prepare_sample() returns -- do not guess.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_spin_gso")
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get("gso_sootheze_cold_therapy_elephant")

smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=v)
print("  scen.sample():")
print("    support_visual_path =", getattr(smp, "support_visual_path", "MISSING"))
print("    support_material    =", getattr(smp, "support_material", "MISSING"))
print("    support_asset_id    =", getattr(smp, "support_asset_id", "MISSING"))

# what does the turntable scenario do?
import inspect
from physim.scenarios import turntable
src = inspect.getsource(turntable)
for i, line in enumerate(src.splitlines(), 1):
    if "support_material" in line or "support_visual_path" in line:
        print(f"    turntable.py:{i}: {line.strip()}")
PY

echo
echo "=== how does generate.py get its sample? ==="
grep -n 'prepare_sample\|support_material\|def prepare_sample' src/physim/pipeline.py | head -20 | sed 's/^/  /'
echo "  --- prepare_sample body (key lines) ---"
awk '/^def prepare_sample/,/^def [a-z_]+\(/' src/physim/pipeline.py | grep -nE 'sample|support|return|Prepared' | head -25 | sed 's/^/    /'
