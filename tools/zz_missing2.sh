#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
echo "=== do the GLB visuals exist? ==="
for a in food_apple food_lime food_lychee special_coffee_cup sphere_baseball sphere_basketball sphere_football sphere_volleyball; do
  printf '  %-22s ' "$a"
  ls -la "$R/assets/objects/$a/visual/" 2>/dev/null | tail -n +4 | awk '{printf "%s(%s) ", $9, $5}'
  echo
done
for a in basketball_court classroom street; do
  printf '  %-22s ' "$a"
  ls -la "$R/assets/environments/$a/visual/" 2>/dev/null | tail -n +4 | awk '{printf "%s(%s) ", $9, $5}'
  echo
done
echo
echo "=== .gitignore (are GLBs/blends excluded?) ==="
cat "$R/.gitignore"
echo
echo "=== git tracked files under assets (if git repo) ==="
cd "$R" && git ls-files assets 2>&1 | head -20 || echo "  not a git repo here"
