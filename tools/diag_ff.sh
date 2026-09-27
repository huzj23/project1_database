#!/usr/bin/env bash
# ===========================================================================
# Why free_fall fails outside_surface_bounds, and what the mentor's own timing is.
#
# Measured: travel 1.632 m, drop_distance 1.583 m -> horizontal drift ~0.40 m
# after the bounce.  The sampler reserves travel_distance = 0 for a vertical drop,
# so the actor may be placed right at the edge (margin = radius + edge_margin) and
# a 0.4 m post-bounce drift carries it out of bounds.
#
# Also check: how many of the 81 frames does the FALL itself occupy?  At 16 fps a
# 1.6 m drop takes 0.571 s = 9 frames, so 72 frames are impact/settle.  The
# mentor's own config shows what he intended.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== mentor's own free_fall.yaml ==="
cat configs/scenarios/free_fall.yaml | sed 's/^/  /'

echo
echo "=== validate_free_fall gates ==="
sed -n '174,234p' src/physim/validation/__init__.py | sed 's/^/  /'
