#!/usr/bin/env bash
# The orbit sweep wrote 0 bytes because its stderr was filtered through
# `grep -E '^TT'`.  Re-run it WITHOUT the filter so the real error is visible.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || { echo "CD FAILED"; exit 1; }

echo "=== sanity: imports + one sample ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys, traceback
sys.path.insert(0, "src")
try:
    from physim.config import load_run_config
    from physim.assets import AssetManager
    from physim.maps import MapManager
    from physim.scenarios import create_scenario, variants_from_config
    from physim.physics.pybullet_backend import PyBulletBackend
    from physim.validation import validate_sample
    from physim.camera import fixed_camera
    print("TT imports ok")
except Exception:
    traceback.print_exc(); raise SystemExit(1)

try:
    am = AssetManager("configs/assets.yaml", "assets")
    mm = MapManager("configs/maps.yaml", am)
    ms = mm.get("replicad_apartment", require_files=True)
    surface = ms.surface("replicad_apartment_table_top")
    asset = am.get("gso_sootheze_cold_therapy_elephant")
    print("TT elephant fp_r=%.5f sh=%.5f" % (asset.footprint_radius, asset.support_height))
    print("TT max orbit = %.4f (frac %.3f)" % (0.30 - asset.footprint_radius,
                                               (0.30 - asset.footprint_radius)/0.30))
    cfg = load_run_config("configs/server.yaml", scenario="turntable_carry_gso")
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=5001, asset=asset, map_spec=ms, variant=v)
    print("TT sample ok orbit_fraction=", getattr(smp, "orbit_radius_fraction", "n/a"))
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    print("TT simulate ok n=", len(res.trajectory))
    rep = validate_sample(res, smp, surface, cfg["validation"])
    print("TT validate valid=", rep.valid, "reasons=", list(rep.reasons))
except Exception:
    traceback.print_exc(); raise SystemExit(1)
PY
echo "EXIT=$?"
