#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# P1.3  Wire our environment + objects into the mentor pipeline and run ONE
#       free_fall smoke sample, to prove PyBullet really integrates motion for
#       OUR assets in OUR scene before building the other six scenarios.
#
# His pipeline is config-driven, so this is config work, not code surgery:
#   1. append the ReplicaCAD map entry to configs/maps.yaml
#   2. add a scenario config selecting OUR GSO asset ids
#   3. run scripts/generate.py under Blender
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

echo "=== 1. append ReplicaCAD map entry ==="
if grep -q '^  replicad_apartment:' configs/maps.yaml; then
  echo "  already present"
else
  cp -f configs/maps.yaml configs/maps.yaml.bak
  cat configs/_map_replicad_snippet.yaml >> configs/maps.yaml
  echo "  appended (backup at configs/maps.yaml.bak)"
fi
"$PY" -c "
import yaml
d = yaml.safe_load(open('configs/maps.yaml'))
print('  maps now:', list(d['maps'].keys()))
"

echo
echo "=== 2. scenario config for our GSO objects ==="
cat > configs/scenarios/free_fall_gso.yaml <<'YAML'
version: 1
scenario: free_fall

controlled_variants:
  variable: gravity
  multipliers: [1.0, 0.5, 1.5]
  labels: [x1, x0.5, x1.5]

selection:
  map_ids: [replicad_apartment]
  asset_ids:
    - gso_sootheze_cold_therapy_elephant

timing:
  duration_seconds: 5.0625
  frame_count: 81
  physics_fps: 240
  video_fps: 16

physics:
  gravity: [0.0, 0.0, -9.81]
  rolling_friction: 0.0
  spinning_friction: 0.0
  horizontal_speed_range: [0.02, 0.08]
  vertical_speed_range: [-0.03, 0.03]
  angular_speed_range: [0.0, 1.5]
  direction_degrees_range: [-180.0, 180.0]
  drop_height_object_extent_range: [2.5, 4.5]
  drop_height_absolute_range: [0.35, 0.90]

surface:
  allowed_types: [floor]
  edge_margin: 0.25

validation:
  min_drop_height: 0.25
  min_drop_distance: 0.20
  max_linear_speed: 8.0
  max_trajectory_extent_object_ratio: 18.0
  max_surface_penetration: 0.04
  require_expected_collision: true
  require_bounce: true
  min_bounce_upward_speed: 0.03
  require_in_map_bounds: true

camera:
  policy: trajectory_side
  relative_to_trajectory: true
  side: random
  azimuth_offset_degrees_range: [-12.0, 12.0]
  focal_length_mm: 50.0
  framing:
    sensor_width_mm: 36.0
    trajectory_frame_fraction: 0.78
    object_padding: 0.30
    min_object_frame_fraction: 0.05
    max_object_frame_fraction: 0.35
    min_object_frame_area_fraction: 0.0025
    max_object_frame_area_fraction: 0.12
    min_distance: 0.40
    max_distance: 8.0
    elevation_degrees: 8.0
    min_height_above_trajectory: 0.15
    look_at_offset: 0.0

output:
  resolution: [1280, 720]
  modalities: [rgb, depth, segmentation]
  save_physics_trajectory: true
  save_render_trajectory: true
  save_collision_events: true
  save_config: true
  write_video: true
YAML
echo "  wrote configs/scenarios/free_fall_gso.yaml"

echo
echo "=== 3. point the run config at OUR scenario file ==="
"$PY" - <<'PYEOF'
import re, pathlib
p = pathlib.Path("configs/server.yaml")
t = p.read_text()
t = re.sub(r"scenario_config: .*", "scenario_config: configs/scenarios/free_fall_gso.yaml", t)
p.write_text(t)
print("  server.yaml scenario_config ->", [l for l in t.splitlines() if "scenario_config" in l][0].strip())
PYEOF

echo
echo "=== 4. smoke run (one group, x1 only) ==="
# NOTE: do NOT pass --scenario.  In load_run_config() an explicit --scenario
# REPLACES project.scenario_config, so "--scenario free_fall" would silently load
# the mentor's own free_fall.yaml (sphere assets) instead of ours.  Omitting it
# lets the scenario_config we just pointed at take effect.
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml \
  --seed 1000 \
  --variant x1 2>&1 | tail -30
