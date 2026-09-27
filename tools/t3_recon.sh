#!/usr/bin/env bash
# ===========================================================================
# T3 RECON: what already exists for the turntable, and what must be extended.
#
# Motions #5 (圆周, object carried by a spinning disc) and #6 (转盘自转, the disc
# alone) are the hardest tier because the physics backend creates exactly ONE
# dynamic body and simulate() returns ONE trajectory; Blender then replays ONE
# object's keyframes.  #5 needs two dynamic bodies (driven disc + free object).
#
# Recover the frozen turntable work and the exact extension points.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== turntable asset ==="
find assets/objects/turntable -type f | sed 's/^/  /'
echo "  --- asset.yaml ---"
cat assets/objects/turntable/asset.yaml | sed 's/^/  /'
echo "  --- collision/model.urdf ---"
cat assets/objects/turntable/collision/model.urdf | sed 's/^/  /'

echo
echo "=== any turntable scripts left on the server? ==="
ls -la "$WS/tools"/*turntable* "$WS/tools"/tt_* "$WS/code"/*turntable* 2>/dev/null | sed 's/^/  /'

echo
echo "=== maps.yaml: does replicad_apartment have a table_top region? ==="
grep -n 'region_id' configs/maps.yaml | sed 's/^/  /'
echo "  --- the replicad_apartment map block ---"
grep -n 'replicad_apartment:' -A40 configs/maps.yaml | sed 's/^/  /'

echo
echo "=== physics backend: the single-body construction ==="
sed -n '36,80p' src/physim/physics/pybullet_backend.py | sed 's/^/  /'
