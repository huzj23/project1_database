#!/usr/bin/env bash
# ===========================================================================
# FULL preflight: sample -> simulate -> validate -> CAMERA, for every clip.
#
# The previous preflight stopped at validate, so rolling clips 2 and 3 passed it
# and then died 5 s into the real run at the camera solver.  Adding the camera call
# makes a framing rejection cost ~1 s instead of a 23-minute render.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^R |^TOTAL'
import sys, math
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config, reference_variant
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import perpendicular_camera

CASES = [
    ("rolling",        "rolling_gso",        "gso_whey_protein_vanilla",                  1001),
    ("rolling",        "rolling_gso",        "gso_room_essentials_fabric_cube_lavender", 1002),
    ("rolling",        "rolling_gso",        "gso_ecoforms_plant_container_gp16a_coral", 1003),
    ("constant_force", "constant_force_gso", "gso_room_essentials_fabric_cube_lavender", 2001),
    ("constant_force", "constant_force_gso", "gso_whey_protein_vanilla",                  2002),
    ("constant_force", "constant_force_gso", "gso_ecoforms_plant_container_gp16a_coral", 2003),
    ("free_fall",      "free_fall_gso",      "gso_down_to_earth_orchid_pot_ceramic_lime", 3001),
    ("free_fall",      "free_fall_gso",      "gso_ecoforms_plant_container_gp16a_coral",  3002),
    ("free_fall",      "free_fall_gso",      "gso_mad_gab_refresh_card_game",             3003),
    ("damping",        "damping_gso",        "gso_whey_protein_vanilla",                  7001),
    ("damping",        "damping_gso",        "gso_room_essentials_fabric_cube_lavender",  7002),
    ("free_fall",      "projectile_gso",     "gso_mad_gab_refresh_card_game",             4001),
    ("free_fall",      "projectile_gso",     "gso_ecoforms_plant_container_gp16a_coral",  4002),
    ("free_fall",      "projectile_gso",     "gso_down_to_earth_orchid_pot_ceramic_lime", 4003),
]

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
npass = 0
for scen_name, cfg_name, aid, seed in CASES:
    cfg = load_run_config("configs/server.yaml", scenario=cfg_name)
    asset = am.get(aid)
    try:
        scen = create_scenario(cfg)
        vs = variants_from_config(cfg)
        v = next((x for x in vs if x.multiplier == 1.0), vs[0])
        smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
        res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
        rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
        if not rep.valid:
            print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} PHYSICS FAIL {list(rep.reasons)}")
            continue
        # the step that was missing before
        cam = perpendicular_camera(
            res, smp, ms.surface(smp.surface_id),
            cfg["camera"], reference_variant(cfg), cfg.get("camera_reference"),
        )
        npass += 1
        f = cam.framing
        print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} PASS "
              f"dist={f.get('distance'):.2f} objfrac={f.get('object_frame_fraction', 0):.4f}")
    except Exception as e:
        print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} ERROR {type(e).__name__}: {str(e)[:110]}")
print(f"TOTAL {npass}/{len(CASES)} PASS (physics + camera)")
PY
