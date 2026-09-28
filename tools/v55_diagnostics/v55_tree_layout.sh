#!/usr/bin/env bash
# Clarify the code/ tree layout: is code/vendor a symlink, a separate checkout, or a
# copy?  And does the MAIN project tree differ from local at all?
WS=/data/raw/huzijian/project1_database
echo "=== code/ layout ==="
ls -la "$WS/code" | sed 's/^/  /'
echo
echo "=== is code/vendor/phyco-sim a symlink? ==="
ls -ld "$WS/code/vendor" "$WS/code/vendor/phyco-sim" 2>&1 | sed 's/^/  /'
readlink -f "$WS/code/vendor/phyco-sim" 2>&1 | sed 's/^/  realpath: /'
echo
echo "=== git status INSIDE code/vendor/phyco-sim (is it its own repo?) ==="
if [ -d "$WS/code/vendor/phyco-sim/.git" ]; then
  git -C "$WS/code/vendor/phyco-sim" rev-parse HEAD 2>&1 | sed 's/^/  HEAD: /'
  git -C "$WS/code/vendor/phyco-sim" remote -v 2>&1 | head -2 | sed 's/^/  /'
else
  echo "  no .git -> it is a plain copy, not a repo"
fi
echo
echo "=== the MAIN project tree: any non-dataset differences? ==="
echo "  (only .pytest_cache appeared in the diff; confirm the main src/ is identical)"
find "$WS/code/physics-video-sim/physics-video-sim-main/src" -name '*.py' \
  -not -path '*/__pycache__/*' | wc -l | sed 's/^/  src python files: /'
echo
echo "=== the third_party tree the project actually uses ==="
ls -ld "$WS/code/physics-video-sim/physics-video-sim-main/third_party"/* 2>&1 | sed 's/^/  /'
readlink -f "$WS/code/physics-video-sim/physics-video-sim-main/third_party/phyco-sim" 2>&1 | sed 's/^/  phyco-sim -> /'
