#!/usr/bin/env bash
# ===========================================================================
# BENCHMARK + regression: run the REAL pipeline end-to-end at the target spec
# (1920x1080) and time it, so tonight's plan rests on a measured number rather
# than a guess.
#
# Also proves the pipeline still runs after this session's edits.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== target spec in free_fall_gso.yaml ==="
grep -E 'resolution|frame_count|video_fps|duration' configs/scenarios/free_fall_gso.yaml | sed 's/^/  /'
grep -E 'samples_per_pixel|engine|device' configs/server.yaml | sed 's/^/  /'

# clean the target sample dir (DatasetWriter uses mkdir(exist_ok=False))
rm -rf datasets/free_fall/seed-009000

echo
echo "=== running the real pipeline (timed) ==="
START=$(date +%s)
"$WS/tools/conda_env/bin/python" scripts/generate.py \
    --config configs/server.yaml --seed 9000 --variant x1 \
    > "$WS/tmp/bench.log" 2>&1
RC=$?
END=$(date +%s)
ELAPSED=$((END - START))

echo "  exit=$RC  elapsed=${ELAPSED}s"
echo "  --- tail of log ---"
tail -6 "$WS/tmp/bench.log" | sed 's/^/    /'

echo
echo "=== produced sample ==="
find datasets/free_fall/seed-009000 -type f 2>/dev/null | sed 's/^/  /'
N=$(ls datasets/free_fall/seed-009000/x1/rgb 2>/dev/null | wc -l)
echo "  rgb frames: $N"
if [ "$N" -gt 0 ] && [ "$ELAPSED" -gt 0 ]; then
  echo "  ==> $(echo "scale=2; $ELAPSED/$N" | bc) s/frame at 1920x1080"
  echo "  ==> 81-frame clip would be $(echo "scale=1; 81*$ELAPSED/$N/60" | bc) min"
fi

echo
echo "=== validation verdict ==="
"$WS/tools/conda_env/bin/python" -c "
import json
m = json.load(open('datasets/free_fall/seed-009000/x1/metadata.json'))
v = m.get('validation', {})
print('  valid =', v.get('valid'))
print('  reasons =', v.get('reasons'))
print('  metrics =', json.dumps(v.get('metrics', {}), indent=2)[:600])
" 2>&1 | sed 's/^/  /'
