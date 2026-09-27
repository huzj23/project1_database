#!/usr/bin/env bash
# ===========================================================================
# Stop the run, then compare my camera gates against the mentor's originals.
#
# Failure: "projected fraction 0.0907, minimum 0.1000".
# From camera/__init__.py:
#     frame_width            = 2 * distance * tangent
#     object_frame_fraction  = max_object_extent / frame_width
#     distance >= content_width / (2 * tangent * trajectory_frame_fraction)
# so at the fit distance
#     object_frame_fraction = max_object_extent * trajectory_frame_fraction
#                             / content_width
# A LONG trajectory inflates content_width and shrinks the object's projected
# fraction.  min_object_frame_fraction is MY choice in the *_gso.yaml files -- the
# mentor's own configs show what value the pipeline was designed around.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== stop the T1 run ==="
tmux kill-session -t t1 2>/dev/null && echo "  t1 stopped" || echo "  t1 was not running"
pkill -9 -f "generate.py" 2>/dev/null
sleep 2
echo "  remaining generate.py: $(pgrep -cf generate.py)"

echo
echo "=== mentor's camera framing gates (all his configs) ==="
for f in rolling constant_force free_fall; do
  echo "--- $f.yaml ---"
  sed -n '/^camera:/,/^output:/p' "configs/scenarios/$f.yaml" | grep -E 'focal|min_object_frame_fraction|max_object_frame_fraction|trajectory_frame_fraction|min_object_frame_area|max_object_frame_area|min_distance|max_distance' | sed 's/^/    /'
done

echo
echo "=== my camera framing gates ==="
for f in rolling_gso constant_force_gso free_fall_gso damping_gso projectile_gso; do
  echo "--- $f.yaml ---"
  sed -n '/^camera:/,/^output:/p' "configs/scenarios/$f.yaml" | grep -E 'focal|min_object_frame_fraction|max_object_frame_fraction|trajectory_frame_fraction|min_distance|max_distance' | sed 's/^/    /'
done
