#!/usr/bin/env bash
# Package the smoke sample for local review: video + a few frames + the JSONs.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"
OUT="$WS/outcomes/_P1_smoke"
rm -rf "$OUT"; mkdir -p "$OUT"

cp -f "$D/video.mp4"        "$OUT/" 2>/dev/null
cp -f "$D/trajectory.json"  "$OUT/" 2>/dev/null
cp -f "$D/collisions.json"  "$OUT/" 2>/dev/null
cp -f "$D/metadata.json"    "$OUT/" 2>/dev/null
cp -f "$D/config.yaml"      "$OUT/" 2>/dev/null

# a spread of frames so the fall + bounce is visible
for i in 00000 00005 00010 00020 00035 00050 00070 00080; do
  f="$D/rgb/rgb_$(printf '%05d' $((10#$i)) ).png"
  [ -f "$f" ] || f="$D/rgb/rgb_$(printf '%05d' $((10#$i + 1))).png"
  [ -f "$f" ] && cp -f "$f" "$OUT/frame_$i.png"
done

echo "=== packaged ==="
ls -la "$OUT" | tail -n +4 | awk '{printf "  %-22s %8.1f KB\n", $9, $5/1024}'
echo "  total: $(du -sh "$OUT" | cut -f1)"
