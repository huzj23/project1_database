#!/usr/bin/env bash
# Locate ScenarioSample / SimulationResult definitions and their full fields.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== where are the dataclasses defined? ==="
grep -rn 'class ScenarioSample\|class SimulationResult\|class TrajectoryState\|class CollisionEvent' src/ | sed 's/^/  /'

echo
echo "=== ScenarioSample full definition ==="
f=$(grep -rln 'class ScenarioSample' src/ | head -1)
echo "  file: $f"
grep -n 'class ScenarioSample' -A50 "$f" | sed 's/^/  /'

echo
echo "=== SimulationResult full definition ==="
g=$(grep -rln 'class SimulationResult' src/ | head -1)
echo "  file: $g"
grep -n 'class SimulationResult' -A25 "$g" | sed 's/^/  /'

echo
echo "=== TrajectoryState ==="
h=$(grep -rln 'class TrajectoryState' src/ | head -1)
echo "  file: $h"
grep -n 'class TrajectoryState' -A18 "$h" | sed 's/^/  /'
