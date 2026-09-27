#!/usr/bin/env bash
# What EXACTLY must be added for the 4 new motions?  Map the gaps precisely.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== ScenarioSample fields (what a scenario may pass to physics) ==="
grep -n 'class ScenarioSample' -A45 "$REPO/src/physim/scenarios/__init__.py" | sed 's/^/  /'

echo
echo "=== BodyState / SimulationResult fields ==="
grep -n 'class BodyState' -A18 "$REPO/src/physim/physics/__init__.py" | sed 's/^/  /'
