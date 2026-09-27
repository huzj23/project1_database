#!/usr/bin/env bash
# ===========================================================================
# FULL preflight (corrected): sample -> simulate -> validate -> CAMERA.
#
# perpendicular_camera(result, config, *, max_object_extent=None) -- two positional
# args only.  config is the scenario's `camera` block, and the camera reference
# variant's trajectory is what the pipeline actually frames (the camera must fit
# the LARGEST variant, not the x1 one).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^R |^TOTAL'
import sys
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
        ref = reference_variant(cfg)          # the camera must fit the LARGEST variant
        # frame the reference variant, as the pipeline does
        smp_ref = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=ref)
        res_ref = PyBulletBackend("third_party/phyco-sim").simulate(smp_ref, ms, asset)
        rep_ref = validate_sample(res_ref, smp_ref, ms.surface(smp_ref.surface_id),
                                  cfg["validation"])
        if not rep_ref.valid:
            print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} REF-VARIANT PHYSICS FAIL "
                  f"{list(rep_ref.reasons)}")
            continue
        cam = perpendicular_camera(res_ref, cfg["camera"],
                                   max_object_extent=cfg["camera"]["framing"].get("max_object_extent"))
        npass += 1
        f = cam.framing
        print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} PASS "
              f"dist={float(f.get('distance', 0)):.2f} "
              f"objfrac={float(f.get('object_frame_fraction', 0)):.4f} "
              f"content_w={float(f.get('content_width', 0)):.3f}")
    except Exception as e:
        print(f"R {scen_name:15s} {aid.replace('gso_',''):40s} ERROR {type(e).__name__}: {str(e)[:110]}")
print(f"TOTAL {npass}/{len(CASES)} PASS (physics + camera)")
PY
