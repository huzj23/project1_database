#!/usr/bin/env bash
# Output inventory + per-run size breakdown for the phase1 delivery.
source /data/raw/huzijian/project1_database/tools/server_env.sh

OUT="$WS/outcomes/dataset/single_object"
echo "=== phase1 delivery ==="
echo "  runs complete : $(find "$OUT" -name metadata.json 2>/dev/null | wc -l) / 36"
echo "  total size    : $(du -sh "$OUT" 2>/dev/null | cut -f1)"

echo
echo "=== aggregate by file kind ==="
for pat in 'rgba_*.png' 'depth_*.png' 'segmentation_*.png' '*.mp4' 'metadata.json' 'qa_contact_sheet.jpg'; do
  n=$(find "$OUT" -name "$pat" 2>/dev/null | wc -l)
  sz=$(find "$OUT" -name "$pat" -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%.1f", s/1048576}')
  printf '  %-22s %5d files  %8s MB\n' "$pat" "$n" "$sz"
done

echo
echo "=== per-run size (first 6) ==="
for d in $(ls -d "$OUT"/*/ 2>/dev/null | head -6); do
  printf '  %-52s %s\n' "$(basename "$d")" "$(du -sh "$d" | cut -f1)"
done

echo
echo "=== small artifacts total (videos + metadata + qa sheets) ==="
find "$OUT" \( -name '*.mp4' -o -name 'metadata.json' -o -name 'qa_contact_sheet.jpg' \) -printf '%s\n' 2>/dev/null |
  awk '{s+=$1} END {printf "  %.1f MB\n", s/1048576}'

echo
echo "=== manifest summary ==="
M="$WS/log/batch_manifest_phase1_20260921.json"
if [ -f "$M" ]; then
  "$WS/tools/conda_env/bin/python" - "$M" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  jobs ok/failed : {m['jobs_ok']}/{m['jobs_failed']}")
print(f"  wall seconds   : {m['wall_seconds']:.0f}  ({m['wall_seconds']/3600:.2f} h)")
secs = [r['seconds'] for r in m['results']]
print(f"  per-video min/max/avg : {min(secs):.0f} / {max(secs):.0f} / {sum(secs)/len(secs):.0f} s")
PY
fi
