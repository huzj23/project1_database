#!/usr/bin/env bash
# Recon 6: kubric PyBullet.run() contact capture + pyco-sim layout.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
K="$REPO/third_party/phyco-sim"
echo "=== A: pyco-sim top ==="
ls -la "$K"
echo "=== B: kubric pybullet.py run ==="
sed -n '180,345p' "$K/kubric/kubric/simulator/pybullet.py"
echo "=== C: collision helpers ==="
grep -n "getContactPoints\|def get_collisions\|contact" "$K/kubric/kubric/simulator/pybullet.py" | head -40
echo "RC RECON6 DONE"
