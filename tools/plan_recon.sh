#!/usr/bin/env bash
# Recon for the 7-motion plan: what already exists vs. what must be written.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== 1) damping / motor support in the physics backend ==="
grep -rn 'linearDamping\|angularDamping\|persistent_force\|applyExternalForce' \
    "$REPO/src/physim/physics/pybullet_backend.py" 2>/dev/null | head -15 | sed 's/^/  /'

echo
echo "=== 2) free_fall: does it already support horizontal velocity (projectile)? ==="
grep -n 'horizontal_speed\|vertical_speed\|angular_speed\|drop_height\|velocity' \
    "$REPO/src/physim/scenarios/free_fall.py" 2>/dev/null | head -25 | sed 's/^/  /'

echo
echo "=== 3) generate.py scenario choices (the gate) ==="
sed -n '14,26p' "$REPO/scripts/generate.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 4) scenario factory ==="
sed -n '88,118p' "$REPO/src/physim/scenarios/__init__.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 5) maps.yaml: replicad_apartment block (does it offer table_top?) ==="
sed -n '225,250p' "$REPO/configs/maps.yaml" 2>/dev/null | sed 's/^/  /'

echo
echo "=== 6) preview.py entry points ==="
grep -n '^def \|^class ' "$REPO/src/physim/preview.py" 2>/dev/null | head -15 | sed 's/^/  /'

echo
echo "=== 7) validator dispatch (how is a scenario's validator chosen?) ==="
sed -n '278,300p' "$REPO/src/physim/validation/__init__.py" 2>/dev/null | sed 's/^/  /'
