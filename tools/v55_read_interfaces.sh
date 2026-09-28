#!/usr/bin/env bash
# V5.5 stage 02: read the ACTUAL interfaces the contract must extend.
# READ-ONLY.
WS=/data/raw/huzijian/project1_database
R="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$R" || exit 1

echo "=== src/physim tree ==="
find src/physim -name '*.py' -not -path '*__pycache__*' | sort | sed 's/^/  /'

echo
echo "=== physics/__init__.py: BodyState + SimulationResult ==="
grep -n 'class BodyState' -A 30 src/physim/physics/__init__.py | sed 's/^/  /'
echo "  ---"
grep -n 'class SimulationResult' -A 25 src/physim/physics/__init__.py | sed 's/^/  /'

echo
echo "=== physics/__init__.py: load_simulation_result ==="
grep -n 'def load_simulation_result' -A 40 src/physim/physics/__init__.py | sed 's/^/  /'

echo
echo "=== scenarios/__init__.py: ScenarioSample ==="
grep -n 'class ScenarioSample' -A 30 src/physim/scenarios/__init__.py | sed 's/^/  /'
