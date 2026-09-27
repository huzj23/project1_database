#!/usr/bin/env bash
# The orbit sweep's last write left the file in a state where my regex no longer
# matches.  Show the ACTUAL physics block so I can see what is there.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== carry: physics block, verbatim ==="
awk '/^physics:/{f=1} f{print NR": "$0} /^surface:/{if(f)exit}' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'

echo
echo "=== grep the two keys ==="
grep -n 'orbit_radius_fraction_range\|angular_speed_range' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'

echo
echo "=== backups available ==="
ls -la "$WS/tmp/carry_orig.yaml" configs/scenarios/turntable_carry_gso.yaml.pre_eleph 2>/dev/null | sed 's/^/  /'

echo
echo "=== restore the pre-sweep version and re-apply the two chosen values ==="
cp "$WS/tmp/carry_orig.yaml" configs/scenarios/turntable_carry_gso.yaml
grep -n 'orbit_radius_fraction_range\|angular_speed_range' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'
