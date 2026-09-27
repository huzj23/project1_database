#!/usr/bin/env bash
# ===========================================================================
# Assess the failed rolling subagent's work + clean up STALE turntable clips.
#
# The subagent failed with no closing message but clearly edited a lot:
#   rolling.py now has resolve_initial_orientation / orientation /
#   collision_simulation_path / _contact_physics, and rolling_gso.yaml now uses
#   `side: random` with azimuth -25..25 instead of the fixed pose I suggested.
# So: find out whether the work is COMPLETE and VALID, or half-finished.
#
# Also: turntable_spin/seed-006002 and seed-006003 are from the earlier subagent
# render and used the OLD trajectory_side camera + non-elephant actors.  They must
# not be confused with the new approved-camera/elephant clips, so remove them.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== does rolling still IMPORT and RUN? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -25
import sys, traceback
sys.path.insert(0, "src")
try:
    from physim.scenarios import create_scenario
    from physim.scenarios.rolling import RollingScenario
    from physim.scenarios.common import resolve_initial_orientation
    print("  imports ok")
except Exception:
    traceback.print_exc(); raise SystemExit(1)

import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
print(f"  rolling_gso actor list = {cfg['selection']['asset_ids']}")
print(f"  orientation block = {cfg.get('physics', {}).get('orientation')}")

for aid in cfg["selection"]["asset_ids"]:
    try:
        asset = am.get(aid)
        smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
        res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
        rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
        p = np.asarray([s.position for s in res.trajectory])
        print(f"  {aid:44s} valid={rep.valid} reasons={list(rep.reasons)}")
        print(f"      quat={tuple(round(x,4) for x in smp.initial_quaternion)} "
              f"support_h={smp.support_height:.5f}")
        print(f"      travel={np.linalg.norm(p[-1]-p[0]):.4f} "
              f"z={p[:,2].min():.5f}..{p[:,2].max():.5f} "
              f"supp={rep.metrics.get('supported_fraction')}")
    except Exception as e:
        print(f"  {aid:44s} ERROR {type(e).__name__}: {str(e)[:110]}")
PY

echo
echo "=== remove STALE turntable_spin clips (old camera, old actors) ==="
for s in 006002 006003; do
  d="datasets/turntable_spin/seed-$s"
  if [ -d "$d" ]; then rm -rf "$d"; echo "  removed $d"; fi
done
echo "  remaining turntable datasets:"
for d in datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  echo "    $(echo $d | sed 's|datasets/||') rgb=$(ls $d/rgb 2>/dev/null | wc -l) mp4=$([ -f $d/video.mp4 ] && echo yes || echo no)"
done

echo
echo "=== rolling datasets (did the subagent render anything?) ==="
ls -d datasets/rolling/seed-* 2>/dev/null | sed 's/^/  /'
echo "  --- outcomes/_t1b ---"
ls -la "$WS/outcomes/_t1b" 2>/dev/null | sed 's/^/  /' || echo "  absent"

echo
echo "=== subagent scratch files ==="
ls -la "$WS/tools"/roll* "$WS/tools"/t1b* 2>/dev/null | sed 's/^/  /' || echo "  none"
ls -la "$REPO"/configs/scenarios/rolling_gso.yaml* 2>/dev/null | sed 's/^/  /'
