#!/usr/bin/env bash
# V5.5 stage 04: full run -- contract regression, solver smoke tests, counter-examples,
# and the step-sensitivity / repeatability evidence.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh

REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
export PYTHONPATH="$REPO/src:${PYTHONPATH:-}"
OUT="$WS/outcomes/v55/stage04"
mkdir -p "$OUT"

echo "=== environment ==="
"$PY" -c "import sys, pybullet; print('python', sys.version.split()[0]); print('pybullet API', pybullet.getAPIVersion())"

echo
echo "=== A. stage 02 contract regression ==="
"$PY" "$WS/tools/v55_test_contracts.py" > "$OUT/contract_tests.log" 2>&1
CONTRACTS_RC=$?
echo "CONTRACTS_RC=$CONTRACTS_RC"
tail -3 "$OUT/contract_tests.log"

echo
echo "=== B. solver smoke tests + validator counter-examples ==="
"$PY" "$WS/tools/v55_test_multibody.py" > "$OUT/multibody_tests.log" 2>&1
MULTI_RC=$?
echo "MULTIBODY_RC=$MULTI_RC"
grep -aE '^\s+\[(PASS|FAIL)\]|^=== SUMMARY' "$OUT/multibody_tests.log"

echo
echo "=== C. step sensitivity and same-seed repeatability ==="
"$PY" "$WS/tools/v55_test_step_sensitivity.py" > "$OUT/step_sensitivity.log" 2>&1
STEP_RC=$?
echo "STEP_RC=$STEP_RC"
grep -aE '^\s+\[(PASS|FAIL)\]|^=== SUMMARY' "$OUT/step_sensitivity.log"

echo
echo "=== overall ==="
echo "contracts=$CONTRACTS_RC multibody=$MULTI_RC step=$STEP_RC"
ls -la "$OUT"
