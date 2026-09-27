#!/usr/bin/env bash
# Recon 5: entry point generate.py + DataSetWriter layout + how clip was produced.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== A: generate.py ==="
cat "$REPO/scripts/generate.py"
echo "=== B: io/__init__.py head ==="
sed -n '1,80p' "$REPO/src/physim/io/__init__.py"
echo "=== C: run scripts that made the clip ==="
cat "$WS/tools/t1_render.sh" 2>/dev/null
echo "--- t1_run.sh ---"
cat "$WS/tools/t1_run.sh" 2>/dev/null
echo "RC RECON5 DONE"
