#!/usr/bin/env bash
# Final inventory before planning:
#  - which STAGES exist (can we export v3_sc0..sc3 scenes?)
#  - do our GSO/sphere objects actually have VISUAL files?
#  - what validators exist in validation/__init__.py?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
R="$WS/models/backgrounds/replicad"

echo "=== stages ==="
ls -1 "$R/stages" 2>/dev/null | sed 's/^/  /'

echo
echo "=== object visual files present? ==="
for d in "$REPO"/assets/objects/*/; do
  n=$(basename "$d")
  vis=$(find "$d" -path '*visual*' -type f 2>/dev/null | head -1)
  col=$(find "$d" -path '*collision*' -type f -name '*.urdf' 2>/dev/null | head -1)
  printf "  %-46s vis=%-38s col=%s\n" "$n" "${vis#$d}" "${col#$d}"
done

echo
echo "=== validators defined ==="
grep -n '^def \|^class ' "$REPO/src/physim/validation/__init__.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=== validator names referenced by scenario configs ==="
grep -rn 'validate_\|validator' "$REPO/src/physim/scenarios/__init__.py" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== does the pipeline have a CLI entrypoint? ==="
ls -1 "$REPO/src/physim/" 2>/dev/null | sed 's/^/  /'
echo "  --- scripts ---"
ls -1 "$REPO/scripts/" 2>/dev/null | head -25 | sed 's/^/    /'
