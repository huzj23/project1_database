#!/usr/bin/env bash
F=/data/raw/huzijian/project1_database/tmp/zz_coll_test/model.obj
echo "=== head ==="; head -8 "$F"
echo "=== counts ==="
for k in v vn vt f; do printf '  %s: ' "$k"; grep -c "^$k " "$F"; done
echo "=== face lines ==="; grep -m3 '^f ' "$F"
echo "=== tail ==="; tail -3 "$F"
echo "=== urdf ==="; cat /data/raw/huzijian/project1_database/tmp/zz_coll_test/model.urdf
echo "=== committed (1968-tri) obj header/counts ==="
G=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/special_plush_elephant/collision/model.obj
head -5 "$G"
for k in v vn vt f; do printf '  %s: ' "$k"; grep -c "^$k " "$G"; done
grep -m2 '^f ' "$G"
