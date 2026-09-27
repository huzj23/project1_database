#!/usr/bin/env bash
# Restore maps.yaml, then show the exact indentation around the join point.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

cp "$WS/tmp/maps_pre_tabletop.bak" configs/maps.yaml
echo "restored; lines = $(wc -l < configs/maps.yaml)"

echo
echo "=== indentation of every 'surface_groups' / '- surface_type' / top-level key ==="
grep -n 'surface_groups\|- surface_type\|^  [a-z_]*:\|^maps:' configs/maps.yaml | cat -A | sed 's/\$$//' | sed 's/^/  /'

echo
echo "=== last 12 lines of the restored file, with visible spaces ==="
tail -12 configs/maps.yaml | cat -A | sed 's/\$$//' | sed 's/^/  /'

echo
echo "=== does it parse now? ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
d=yaml.safe_load(open('configs/maps.yaml'))
print('  OK, maps:', list(d['maps'].keys()))
"
