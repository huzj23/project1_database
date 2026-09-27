#!/usr/bin/env bash
# Recon 4: CLI entry points + cache dirs for rolling.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== A: scripts ==="
ls -la "$REPO/scripts"
echo "=== B: pyproject ==="
cat "$REPO/pyproject.toml"
echo "=== C: cache/rolling ==="
ls -laR "$REPO/cache/rolling" | head -40
echo "=== D: README run section ==="
head -60 "$REPO/README.md"
echo "=== E: tests ==="
ls -la "$REPO/tests"
echo "RC RECON4 DONE"
