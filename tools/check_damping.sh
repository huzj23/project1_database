#!/usr/bin/env bash
# B) Is damping wired in?  And is there a motor/turntable mechanism?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== changeDynamics call site ==="
sed -n '128,162p' "$REPO/src/physim/physics/pybullet_backend.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=== damping anywhere in src/physim? ==="
grep -rn 'damping' "$REPO/src/physim/" 2>/dev/null | sed 's/^/  /'
echo "  ^^^ empty = damping NOT supported yet"

echo
echo "=== the PhysicsSpec / asset physics dataclass fields ==="
grep -rn 'class Physics\|class .*Spec\|friction\|restitution\|mass' \
    "$REPO/src/physim/assets/__init__.py" 2>/dev/null | head -25 | sed 's/^/  /'

echo
echo "=== what does the asset loader read from asset.yaml physics? ==="
grep -rn 'physics' "$REPO/src/physim/assets/__init__.py" 2>/dev/null | head -20 | sed 's/^/  /'
