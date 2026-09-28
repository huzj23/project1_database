#!/usr/bin/env bash
# V5.5 stage 03: determine whether the Hidden Alley / The Shed hash mismatch means
# (a) an incomplete download, (b) a re-downloaded newer revision, or
# (c) extraction of a different member.
#
# Cross-checks against the V5.4 feasibility audit, which recorded facts at planning
# time, and tests archive integrity.  READ-ONLY.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. V5.4 feasibility audit files ==="
ls -la "$WS/outcomes/v54_feasibility/" 2>/dev/null | sed 's/^/  /' || echo "  (missing)"

echo
echo "=== B. what do the audits say about sizes/hashes of these scenes? ==="
for f in "$WS/outcomes/v54_feasibility"/*.json; do
  [ -f "$f" ] || continue
  echo "  --- $(basename "$f") ---"
  "$PY" - "$f" <<'PY' 2>&1 | head -40
import json, sys
d = json.load(open(sys.argv[1]))
def walk(o, path="", depth=0):
    if depth > 3: return
    if isinstance(o, dict):
        for k, v in o.items():
            if any(t in k.lower() for t in ("sha", "hash", "size", "bytes", "path", "file", "blend")):
                if not isinstance(v, (dict, list)):
                    print(f"      {path}{k} = {v}")
            walk(v, f"{path}{k}.", depth + 1)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            walk(v, f"{path}[{i}].", depth + 1)
walk(d)
PY
done

echo
echo "=== C. zip integrity (this is the decisive test) ==="
for z in "$WS/models/backgrounds/candidates/hidden_alley/source/hidden_alley.zip" \
         "$WS/models/backgrounds/candidates/the_shed/source/the_shed.zip"; do
  echo "  --- $(basename "$z") ($(stat -c%s "$z") bytes) ---"
  if command -v unzip >/dev/null 2>&1; then
    unzip -t "$z" 2>&1 | tail -5 | sed 's/^/    /'
  fi
  # 7z gives a stronger test when available.
  if [ -x "$WS/tools/runtime/7z" ] || command -v 7z >/dev/null 2>&1; then
    SEVEN=$(command -v 7z || echo "$WS/tools/runtime/7z")
    "$SEVEN" t "$z" 2>&1 | tail -6 | sed 's/^/    /'
  fi
done

echo
echo "=== D. archive listing: which .blend members exist, and their sizes ==="
for z in "$WS/models/backgrounds/candidates/hidden_alley/source/hidden_alley.zip" \
         "$WS/models/backgrounds/candidates/the_shed/source/the_shed.zip"; do
  echo "  --- $(basename "$z") ---"
  unzip -l "$z" 2>/dev/null | grep -iE '\.blend|Length|----' | head -12 | sed 's/^/    /'
done

echo
echo "=== E. free space (a truncated download is the top hypothesis) ==="
df -h "$WS" | sed 's/^/  /'
echo "  --- sizes of the two archives vs the extracted blends ---"
for d in hidden_alley the_shed; do
  z=$(find "$WS/models/backgrounds/candidates/$d/source" -name '*.zip' | head -1)
  b=$(find "$WS/models/backgrounds/candidates/$d" -name '*.blend' | head -1)
  printf '  %-14s zip=%s  blend=%s\n' "$d" "$(stat -c%s "$z" 2>/dev/null)" "$(stat -c%s "$b" 2>/dev/null)"
done

echo
echo "=== F. is the same archive present in a second location (a good copy)? ==="
find "$WS" -name 'hidden_alley*.zip' -o -name 'the_shed*.zip' 2>/dev/null | sed 's/^/  /'
find "$WS" -name 'ph_hidden_alley*.blend' -o -name 'the_shed*.blend' 2>/dev/null | sed 's/^/  /'
