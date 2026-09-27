#!/usr/bin/env bash
# Extract the pristine upstream zip that was uploaded to tmp/upstream.zip, then
# diff the SERVER tree against it (authoritative side = server, which produced
# every delivered video).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tmp" || exit 1
rm -rf upstream_x
mkdir -p upstream_x
cd upstream_x || exit 1
unzip -q ../upstream.zip
echo "=== extracted ==="
ls | sed 's/^/  /'
echo "  --- scenarios (pristine = upstream's 3 only) ---"
ls physics-video-sim-main/configs/scenarios/ 2>/dev/null | sed 's/^/    /'
echo "  --- README head (identity) ---"
head -20 physics-video-sim-main/README.md 2>/dev/null | sed 's/^/    /'
echo "  --- repo URL in metadata ---"
grep -rhoiE 'github\.com/[A-Za-z0-9_.-]+/physics-video-sim[A-Za-z0-9_./-]*' \
  physics-video-sim-main/ 2>/dev/null | sort -u | head -5 | sed 's/^/    /'
