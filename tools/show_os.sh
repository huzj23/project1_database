#!/usr/bin/env bash
# Show the orbit-sweep log (the previous invocation produced no visible output).
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
echo "=== log size ==="
ls -la "$WS/tmp/os.log" 2>/dev/null | sed 's/^/  /'
echo "=== log content ==="
cat "$WS/tmp/os.log" 2>/dev/null | head -40 | sed 's/^/  /'
echo "=== current carry orbit setting ==="
grep -n 'orbit_radius_fraction_range' "$REPO/configs/scenarios/turntable_carry_gso.yaml" | sed 's/^/  /'
