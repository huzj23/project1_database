#!/usr/bin/env bash
# Full text of the three scenario configs, so the plan can reuse their structure.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
for f in constant_force rolling; do
  echo "=========== $f.yaml ==========="
  cat "$REPO/configs/scenarios/$f.yaml" 2>/dev/null | sed 's/^/  /'
  echo
done
echo "=========== free_fall_gso.yaml (ours, current) ==========="
cat "$REPO/configs/scenarios/free_fall_gso.yaml" 2>/dev/null | sed 's/^/  /'
