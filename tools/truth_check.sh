#!/usr/bin/env bash
# ===========================================================================
# CRITICAL CORRECTNESS CHECK: is my local `code/` checkout stale?
#
# The V3.7 subagent diffed against a pristine upstream zip and reported:
#   * `setTimeStep` does not exist (only a comment)
#   * `physics_fps: 560` is REJECTED by upstream's verbatim `!= 240` guard
#   * `ScenarioSample` has no `orientation` field, so rolling.py crashes
#   * `scenarios/damping.py` does not exist
#
# But I have personally seen, ON THE SERVER, an actual setTimeStep CALL in
# pybullet_backend.py, and the server is rendering rolling with physics_fps 560
# right now.  Those cannot both be true of the same tree.
#
# So: establish which tree is authoritative by diffing local vs server directly.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== SERVER: the physics_fps guard and the setTimeStep call ==="
sed -n '40,80p' src/physim/physics/pybullet_backend.py | cat -n | sed 's/^/  /'

echo
echo "=== SERVER: does ScenarioSample declare orientation? ==="
grep -n 'class ScenarioSample' -A 45 src/physim/scenarios/common.py | grep -nE 'orientation|collision_simulation_path|support_|^.*:' | head -25 | sed 's/^/  /'

echo
echo "=== SERVER: does scenarios/damping.py exist? ==="
ls -la src/physim/scenarios/ | sed 's/^/  /'

echo
echo "=== SERVER: all scenario configs ==="
ls configs/scenarios/ | sed 's/^/  /'

echo
echo "=== SERVER: files under src modified in last 24h ==="
find src configs -name '*.py' -o -name '*.yaml' | xargs ls -la 2>/dev/null | sort -k6,7 | tail -20 | sed 's/^/  /'
