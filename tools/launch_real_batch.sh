#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Launch the "A" main track on the server: GSO scanned actors on a PBR ground
# with an HDRI warehouse backdrop (the approved configuration).
#
# Each shard is an independent Blender process with its own job subset, so the
# batch is parallel without any shared state.
#
#   bash tools/launch_real_batch.sh [shards] [frames] [samples] [resolution]
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

SHARDS="${1:-6}"
FRAMES="${2:-96}"
SPP="${3:-24}"
RES="${4:-1280x720}"
PRESET="${PRESET:-server_a}"
OUT="${OUT:-$WS/outcomes/dataset_real}"
SESSION="phyco_real"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"

echo "=== preflight ==="
if [ ! -x "$BL" ]; then
  echo "  blender not found at $BL"
  echo "  (falling back to the bpy wheel interpreter)"
  BL=""
fi

PY="$WS/tools/conda_env/bin/python"
[ -n "$BL" ] || echo "  using bpy wheel: $PY"

# the actors must be present locally on the server
MISSING=0
for o in Sootheze_Cold_Therapy_Elephant Room_Essentials_Fabric_Cube_Lavender \
         Mad_Gab_Refresh_Card_Game Ecoforms_Plant_Container_GP16A_Coral \
         Down_To_Earth_Orchid_Pot_Ceramic_Lime Whey_Protein_Vanilla; do
  if [ ! -f "$WS/models/gso/$o/data.json" ]; then
    echo "  MISSING: $o"
    MISSING=1
  fi
done
[ "$MISSING" = 0 ] && echo "  all 6 GSO actors present"
[ -f "$WS/models/hdri_hdr/empty_warehouse_01_4k.hdr" ] && echo "  HDRI present" || echo "  MISSING HDRI"
[ -d "$WS/models/pbr_textures/concrete_textures/concrete_floor_worn_001.blend/textures" ] \
  && echo "  PBR ground present" || echo "  MISSING PBR ground"

echo
echo "=== launch: preset=$PRESET shards=$SHARDS frames=$FRAMES spp=$SPP res=$RES ==="
echo "    output: $OUT"

rm -rf "$WS/tmp"/ls_* "$WS/tmp"/phyco_scratch_* 2>/dev/null
mkdir -p "$OUT" "$WS/log"
tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1

for i in $(seq 0 $((SHARDS - 1))); do
  if [ -n "$BL" ]; then
    CMD="\"$BL\" --background --factory-startup --python $WS/code/scenarios/make_local_samples.py -- \
         --preset $PRESET --shard_index $i --shard_total $SHARDS \
         --outcomes $OUT --resolution $RES --samples $SPP --frames $FRAMES"
  else
    CMD="\"$PY\" -u $WS/code/scenarios/make_local_samples.py \
         --preset $PRESET --shard_index $i --shard_total $SHARDS \
         --outcomes $OUT --resolution $RES --samples $SPP --frames $FRAMES"
  fi
  tmux new-session -d -s "${SESSION}_$i" "$CMD > $WS/log/real_shard$i.log 2>&1; echo DONE >> $WS/log/real_shard$i.log"
  echo "  shard $i -> tmux ${SESSION}_$i"
done

sleep 20
echo
echo "=== after 20s ==="
for i in $(seq 0 $((SHARDS - 1))); do
  printf '  shard %s: %s\n' "$i" "$(tail -1 "$WS/log/real_shard$i.log" 2>/dev/null | cut -c1-110)"
done
echo "  running blender procs: $(ps -eo cmd | grep -c '[m]ake_local_samples')"
