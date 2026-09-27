#!/usr/bin/env bash
# ===========================================================================
# VERIFY every shared video really is 1920x1080 / 81 frames, and that each has its
# matching annotation set, BEFORE packaging.  A file merely existing is not proof.
# Then build the zip and report its exact size.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
SHARE="$WS/share_build"
cd "$SHARE" || exit 1

echo "=== video specs ==="
fail=0
for f in $(find videos -name '*.mp4' | sort); do
  info=$(ffprobe -v error -select_streams v:0 -show_entries \
         stream=width,height,nb_frames,r_frame_rate -of csv=p=0 "$f" 2>/dev/null)
  base=$(basename "$f" .mp4)
  dir="annotations/$(dirname "$f" | sed 's|videos/||')/$base"
  n_ann=$(ls "$dir" 2>/dev/null | wc -l)
  nfr=$(echo "$info" | awk -F, '{print $4}')
  w=$(echo "$info" | awk -F, '{print $1}')
  h=$(echo "$info" | awk -F, '{print $2}')
  ok="OK"
  [ "$nfr" = "81" ] || { ok="BAD-FRAMES"; fail=$((fail+1)); }
  [ "$w" = "1920" ] && [ "$h" = "1080" ] || { ok="BAD-RES"; fail=$((fail+1)); }
  [ "$n_ann" -ge 4 ] || { ok="MISSING-ANNOT"; fail=$((fail+1)); }
  printf "  %-46s %sx%s %3s frames  ann=%d  %s\n" "$f" "$w" "$h" "$nfr" "$n_ann" "$ok"
done
echo "  failures: $fail"

echo
echo "=== per-video annotation completeness ==="
for d in $(find annotations -mindepth 2 -maxdepth 2 -type d | sort); do
  printf "  %-58s %s\n" "$d" "$(ls $d | tr '\n' ' ')"
done

echo
echo "=== metadata sanity: every sample valid? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, json, os
SHARE = "/data/raw/huzijian/project1_database/share_build"
bad = 0; n = 0
for p in sorted(glob.glob(SHARE + "/annotations/*/*/metadata.json")):
    j = json.load(open(p))
    v = j.get("validation", {})
    n += 1
    if not v.get("valid"):
        bad += 1
        print(f"  INVALID {p}: {v.get('reasons')}")
print(f"  {n} metadata files, {bad} invalid")
# report camera + lighting provenance for the record
print("  --- lighting provenance (iron rule 4) ---")
seen = set()
for p in sorted(glob.glob(SHARE + "/annotations/*/*/metadata.json")):
    R = json.load(open(p)).get("render", {})
    key = (R.get("environment_lighting_source"), R.get("environment_light_count"))
    seen.add(key)
for k in sorted(seen, key=str):
    print(f"    source={k[0]}  authored_lights={k[1]}")
PY

echo
echo "=== PACKAGE ==="
cd "$WS" || exit 1
rm -f share_build.zip
cd share_build || exit 1
zip -qr ../share_build.zip . -x '.*' 
cd "$WS" || exit 1
ls -la share_build.zip | awk '{printf "  share_build.zip = %.2f MB\n", $5/1048576}'
echo "  (limit 50 MB)"
echo
echo "=== zip integrity ==="
unzip -t share_build.zip 2>&1 | tail -2 | sed 's/^/  /'
echo "  entries: $(unzip -l share_build.zip | tail -1 | awk '{print $2}')"
