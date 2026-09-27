#!/usr/bin/env bash
# ===========================================================================
# T2 DAMPING: recon the exact integration points before writing code.
#
# Damping is a solver parameter (Bullet's linearDamping/angularDamping), so the
# motion stays genuinely simulated: we set the coefficient once and Bullet
# integrates the decay.  Probe 2 measured that it works (k=0.4 gave a clean
# monotonic decay) and that k>=1.2 stopped the body immediately, so the usable
# band is roughly 0.1-1.0.
#
# Need to know:
#   1. ScenarioSample fields (to add damping)
#   2. SimulationResult / how the backend reports
#   3. the exact changeDynamics call site
#   4. the scenario factory dispatch
#   5. validate_sample dispatch
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1) ScenarioSample dataclass ==="
grep -n 'class ScenarioSample' -A45 src/physim/scenarios/common.py | sed 's/^/  /'

echo
echo "=== 2) scenario factory dispatch ==="
sed -n '85,115p' src/physim/scenarios/__init__.py | sed 's/^/  /'

echo
echo "=== 3) validate_sample dispatch ==="
sed -n '270,300p' src/physim/validation/__init__.py | sed 's/^/  /'

echo
echo "=== 4) changeDynamics call site ==="
grep -n 'changeDynamics' -B4 -A12 src/physim/physics/pybullet_backend.py | sed 's/^/  /'
