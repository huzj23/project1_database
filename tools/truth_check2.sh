#!/usr/bin/env bash
# ===========================================================================
# The V3.7 subagent diffed a STALE LOCAL checkout and therefore reported three
# "corrections" that are FALSE for the tree that actually produced our videos:
#   * it said setTimeStep does not exist            -> it DOES (server line 73)
#   * it said physics_fps 560 is rejected by `!=240` -> server relaxed it to `<240`
#   * it said scenarios/damping.py is missing        -> it EXISTS (5.3 KB)
#   * it said projectile_gso.yaml is missing         -> it EXISTS
#
# The server is authoritative: it is what rendered all 12+ clips.  So:
#   (1) confirm the ScenarioSample / orientation claim against the SERVER tree,
#   (2) report the exact local-vs-server divergence so the local copy can be fixed.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== SERVER: ScenarioSample field list ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys, dataclasses
sys.path.insert(0, "src")
from physim.scenarios.common import ScenarioSample
names = [f.name for f in dataclasses.fields(ScenarioSample)]
print(f"  total fields: {len(names)}")
for k in ("orientation", "collision_simulation_path", "support_trajectory",
          "support_visual_path", "support_asset_id", "material_class",
          "support_render_import_kwargs", "support_collision_simulation_path"):
    print(f"    {k:36s} {'PRESENT' if k in names else 'absent'}")
print("  all fields:")
print("   ", ", ".join(names))
PY

echo
echo "=== SERVER: does rolling sampling actually RUN? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -12
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
scen = create_scenario(cfg)
v = variants_from_config(cfg)[0]
asset = am.get("gso_whey_protein_vanilla")
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
print("  rolling sample OK (no TypeError)")
print(f"    physics_fps={smp.physics_fps} video_fps={smp.video_fps} frames={smp.frame_count}")
print(f"    support_height={smp.support_height:.5f} quat={tuple(round(x,4) for x in smp.initial_quaternion)}")
PY

echo
echo "=== local vs server: which files differ? ==="
for f in src/physim/physics/pybullet_backend.py src/physim/scenarios/common.py \
         src/physim/scenarios/rolling.py src/physim/scenarios/__init__.py \
         src/physim/camera/__init__.py src/physim/pipeline.py \
         configs/scenarios/rolling_gso.yaml; do
  s=$(md5sum "$f" 2>/dev/null | awk '{print $1}')
  echo "  $f  server=$s"
done
