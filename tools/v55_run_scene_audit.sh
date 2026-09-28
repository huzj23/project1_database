#!/usr/bin/env bash
# V5.5 stage 03: run the content-level scene audit under the server Blender.
#
# Each scene is audited in its OWN Blender process, because Blender 3.4.1 SEGFAULTED
# (rc=139) opening Hidden Alley after Italian Flat in one process.  Process isolation
# means a crash is contained and the other scenes still produce evidence.
#
# Argument passing uses Blender's standard idiom -- everything after a bare ``--`` is
# delivered to the script.  An earlier attempt set ``sys.argv`` inside --python-expr and
# then called runpy, but runpy re-prepends Blender's own argv, so the script's ``--``
# lookup found nothing and argparse failed with exit 2.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$REPO" || exit 1

OUT="$WS/outcomes/v55/bootstrap/20260928T194500"
mkdir -p "$OUT"
LOG="$OUT/03_scene_content_audit.console.log"
: > "$LOG"

echo "blender: $("$BLENDER" --version 2>&1 | head -1)" | tee -a "$LOG"

run_scene() {
  local name="$1"
  echo "" | tee -a "$LOG"
  echo "########## $name (own process) ##########" | tee -a "$LOG"
  "$BLENDER" --background --factory-startup \
      --python "$WS/tools/v55_audit_scenes_one.py" -- --scene "$name" 2>&1 \
    | grep -aE '^(AUDIT_RECORD|=====|  [a-z]|Error|Traceback)' | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  echo "  [blender exit ${rc}]" | tee -a "$LOG"
  if [ "$rc" -ne 0 ]; then
    echo "  !! non-zero exit (segfault would be 139)" | tee -a "$LOG"
    # Record the failure so the evidence file shows which scene failed.
    printf '{"name":"%s","error":"blender_exit_%s"}\n' "$name" "$rc" \
      >> "$OUT/03_scene_content_audit.jsonl"
  fi
}

# Fresh evidence file for this attempt; keep any previous one.
if [ -f "$OUT/03_scene_content_audit.jsonl" ]; then
  mv "$OUT/03_scene_content_audit.jsonl" \
     "$OUT/03_scene_content_audit.jsonl.prev.$(date +%H%M%S)"
fi
: > "$OUT/03_scene_content_audit.jsonl"

for s in italian_flat hidden_alley the_shed; do
  run_scene "$s"
done

echo "" | tee -a "$LOG"
echo "=== collected records ===" | tee -a "$LOG"
cat "$OUT/03_scene_content_audit.jsonl" | tee -a "$LOG"
