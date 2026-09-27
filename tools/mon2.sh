#!/usr/bin/env bash
# ===========================================================================
# (a) Monitor the red-wood renders.
# (b) Fix a state-pollution issue MY runner introduced: tt_wood_render.sh does
#     `sed -i` on configs/server.yaml to rewrite scenario_config, but it then calls
#     generate.py with configs/server_turntable_*.yaml (which already carry the right
#     scenario_config).  So the sed is unnecessary AND it leaves server.yaml pointing
#     at whichever turntable scenario ran LAST -- wrong for any later run that uses
#     server.yaml directly.  Restore it to the rolling/scenario default and report.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== red-wood render status ==="
cat "$WS/tmp/ttwood_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "  running: $(pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -1)"
echo "  elapsed: $(ps -o etime= -p $(pgrep -f 'scripts/generate.py' | head -1) 2>/dev/null | tr -d ' ')"
echo "  --- completed clips so far ---"
for d in "$REPO"/datasets/turntable_*/seed-*/x1; do
  [ -d "$d" ] || continue
  printf "    %-44s rgb=%s mp4=%s\n" "$(echo $d | sed "s|$REPO/datasets/||")" \
    "$(ls $d/rgb 2>/dev/null | wc -l)" "$([ -f $d/video.mp4 ] && echo yes || echo no)"
done

echo
echo "=== configs/server.yaml scenario_config (state pollution check) ==="
grep -n 'scenario_config' configs/server.yaml | sed 's/^/  /'
echo "  --- backups available ---"
ls configs/server.yaml* 2>/dev/null | sed 's/^/    /'
echo "  --- what the per-scenario configs say (these are what actually ran) ---"
grep -n 'scenario_config' configs/server_turntable_carry.yaml configs/server_turntable_spin.yaml | sed 's/^/    /'
