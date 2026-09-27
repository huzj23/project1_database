#!/usr/bin/env bash
# ===========================================================================
# FAST PRE-FLIGHT: physics+validation for all 9 T1 samples, no rendering.
#
# Rendering is ~15 s/frame -> 20 min per clip, 3 h for 9 clips.  This harness runs
# the identical scenario / backend / validator in ~1 s per sample, so no render
# time is spent on a sample that would be rejected.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^R|^=|^TOTAL'
import sys, math
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

CASES = [
    ("rolling",        "rolling_gso",        "gso_whey_protein_vanilla",                    1001),
    ("rolling",        "rolling_gso",        "gso_room_essentials_fabric_cube_lavender",   1002),
    ("rolling",        "rolling_gso",        "gso_ecoforms_plant_container_gp16a_coral",   1003),
    ("constant_force", "constant_force_gso", "gso_room_essentials_fabric_cube_lavender",   2001),
    ("constant_force", "constant_force_gso", "gso_whey_protein_vanilla",                    2002),
    ("constant_force", "constant_force_gso", "gso_ecoforms_plant_container_gp16a_coral",   2003),
    ("free_fall",      "free_fall_gso",      "gso_down_to_earth_orchid_pot_ceramic_lime",   3001),
    ("free_fall",      "free_fall_gso",      "gso_ecoforms_plant_container_gp16a_coral",    3002),
    ("free_fall",      "free_fall_gso",      "gso_mad_gab_refresh_card_game",               3003),
]

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
npass = 0
for scen_name, cfg_name, aid, seed in CASES:
    cfg = load_run_config("configs/server.yaml", scenario=cfg_name)
    scen = create_scenario(cfg)
    asset = am.get(aid)
    vs = variants_from_config(cfg)
    v = next((x for x in vs if x.multiplier == 1.0), vs[0])
    try:
        smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
        res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
        rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
        ok = rep.valid
        npass += ok
        m = rep.metrics
        print("R %-15s %-42s seed=%-5d %s" % (
            scen_name, aid.replace("gso_", ""), seed, "PASS" if ok else "FAIL " + str(list(rep.reasons))))
        print("R     frames=%d travel=%.3f sup=%.3f extent=%.2f drop=%.3f pen=%.4f" % (
            len(res.trajectory), m.get("travel_distance", 0), m.get("supported_fraction", 0),
            m.get("trajectory_extent_object_ratio", 0), m.get("drop_distance", 0),
            m.get("max_surface_penetration", 0)))
    except Exception as e:
        print("R %-15s %-42s seed=%-5d ERROR %s" % (scen_name, aid.replace("gso_", ""), seed, e))
print("=" * 70)
print("TOTAL %d/%d PASS" % (npass, len(CASES)))
PY
