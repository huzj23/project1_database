#!/usr/bin/env bash
# ===========================================================================
# Fix the skip bug: archive the OLD-camera rolling clip and render camera C.
#
# Confirmed by metadata: datasets/rolling/seed-001001/x1 was rendered with
#   position (-0.6430, 0.7997, 0.4581), focal 40, framing mode
#   `trajectory_and_max_object` -- i.e. the OLD trajectory_side pose the user
#   rejected ("我不喜欢现在离的这么近的左侧自行车").  Camera C is
#   (-0.6744, -3.1931, 0.6127) focal 50, mode `fixed_authored_pose`.
#
# My runner skipped it because the skip test only asked "does video.mp4 exist with
# 81 frames", not "was it rendered with the camera we now require".  The old clip is
# ARCHIVED (not deleted) so the before/after can still be compared, and the sample
# is re-rendered with camera C.
#
# Waits for the in-flight damping render first: two concurrent Cycles jobs contend,
# and concurrent generate.py runs have corrupted the shared cache before.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== t3 status ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "=== t1c status ==="
cat "$WS/tmp/t1c_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "  running: $(pgrep -af 'generate.py' | grep -v 'bash -c' | head -1)"

echo
echo "=== waiting for the machine to be free ==="
for i in $(seq 1 300); do
  if ! pgrep -f 'scripts/generate.py' > /dev/null; then echo "  free after ${i}0s"; break; fi
  sleep 10
done

echo
echo "=== archive the OLD-camera clip (not deleted) ==="
OLD="datasets/rolling/seed-001001"
ARCH="$WS/tmp/old_camera_rolling_clip"
mkdir -p "$ARCH"
if [ -d "$OLD" ]; then
  rm -rf "$ARCH/seed-001001"
  mv "$OLD" "$ARCH/seed-001001"
  echo "  moved $OLD -> $ARCH/seed-001001"
  echo "  archived video: $(ls -la $ARCH/seed-001001/video.mp4 2>/dev/null | awk '{print $5" bytes"}')"
else
  echo "  $OLD absent (already archived?)"
fi

echo
echo "=== render motion #1 匀速 with CAMERA C ==="
sed -i "s|^  scenario_config: .*|  scenario_config: configs/scenarios/rolling_gso.yaml|" configs/server.yaml
grep -E '^\s*scenario_config:' configs/server.yaml | sed 's/^/  /'
LOG="$WS/tmp/rolling_camC.log"; : > "$LOG"
t0=$(date +%s)
"$WS/tools/conda_env/bin/python" scripts/generate.py \
    --config configs/server.yaml \
    --seed 1001 --variant x1 --asset-id gso_whey_protein_vanilla >> "$LOG" 2>&1
rc=$?
t1=$(date +%s)
echo "  rc=$rc elapsed=$((t1-t0))s"

D="datasets/rolling/seed-001001/x1"
echo "  rgb=$(ls $D/rgb 2>/dev/null | wc -l) depth=$(ls $D/depth 2>/dev/null | wc -l) seg=$(ls $D/segmentation 2>/dev/null | wc -l)"
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
d = "datasets/rolling/seed-001001/x1"
if not os.path.isfile(d + "/metadata.json"):
    print("  NO metadata -> render failed"); raise SystemExit
m = json.load(open(d + "/metadata.json"))
R = m["render"]
pos = R.get("camera_position")
print(f"  camera_position = {[round(v,4) for v in pos]}")
print(f"  camera_focal    = {R.get('camera_focal_length_mm')}")
print(f"  lighting        = {R.get('environment_lighting_source')} "
      f"count={R.get('environment_light_count')} types={R.get('environment_light_types')}")
v = m.get("validation", {})
print(f"  valid={v.get('valid')} reasons={list(v.get('reasons', []))}")
isC = (abs(pos[0]+0.6744) < 1e-2 and abs(pos[1]+3.1931) < 1e-2 and abs(pos[2]-0.6127) < 1e-2)
print(f"  IS CAMERA C: {isC}")
PY
