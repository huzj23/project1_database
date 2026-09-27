#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run PhyCo-Sim simulation batches on the shared GPU server.
#
# Uses the workspace-local conda environment (bpy installed as a wheel), so no
# Blender executable and no `--background --python ... --` wrapper is involved.
#
# Everything read or written stays inside:
#   /data/raw/huzijian/project1_database/
#
# Usage (inside tmux):
#   bash tools/run_server.sh smoke
#   bash tools/run_server.sh phase1
#   GPU=1 WORKERS=2 bash tools/run_server.sh phase1
#
# Environment:
#   GPU      physical GPU index to pin to      (default 0)
#   WORKERS  parallel simulation processes     (default 3)
#   RES/SPP  resolution / samples              (default 768x432 / 64)
#   NO_HDRI  1 -> analytic lighting instead of HDRI
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

PRESET="${1:-${PRESET:-smoke}}"
GPU="${GPU:-0}"
WORKERS="${WORKERS:-3}"
RES="${RES:-1280x720}"
SPP="${SPP:-24}"
NO_HDRI="${NO_HDRI:-0}"
LOOK="${LOOK:-studio}"
FRAME_FORMAT="${FRAME_FORMAT:-png}"
MOTION_BLUR="${MOTION_BLUR:-0.25}"

PY="$WS/tools/conda_env/bin/python"
RUNNER="$WS/code/scenarios/generate_batch.py"
LOGDIR="$WS/log"
mkdir -p "$LOGDIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$LOGDIR/batch_${PRESET}_${STAMP}.log"

if [ ! -x "$PY" ]; then
  echo "ERROR: conda env python missing at $PY" >&2
  exit 1
fi
if [ ! -f "$RUNNER" ]; then
  echo "ERROR: runner missing at $RUNNER" >&2
  exit 1
fi

# --- render configuration ----------------------------------------------------
# CPU rendering is used deliberately, NOT as a fallback:
#   * Blender 3.4's CUDA path segfaults as soon as the Depth pass is enabled
#     (reproduced for depth-only, image+depth and all-layers; RGB+seg is fine).
#     Depth is part of the required annotation, so GPU rendering is unusable.
#   * Even where it does work the GPU is only ~13% faster on these small scenes
#     (2.68 vs 3.07 s/frame at 768x432/64spp) because per-frame cost is dominated
#     by EXR I/O and compositing rather than ray tracing.
#   * This node has 104 cores, so parallel CPU workers win by a wide margin.
export CUDA_VISIBLE_DEVICES="$GPU"      # kept set so any future GPU pass can use it
export KUBRIC_USE_GPU=false
export PHYCO_PYTHON="$PY"
export PYTHONUNBUFFERED=1

# Blender otherwise starts one thread per core inside EVERY worker; divide the
# machine between them so parallel runs do not thrash.
CORES="$(nproc 2>/dev/null || echo 8)"
THREADS="${THREADS:-$(( CORES / (WORKERS > 0 ? WORKERS : 1) ))}"
[ "$THREADS" -lt 1 ] && THREADS=1
export OMP_NUM_THREADS="$THREADS"

EXTRA=()
[ "$NO_HDRI" = "1" ] && EXTRA+=(--no_hdri)

{
  echo "=============================================================="
  echo "[run] $(date '+%F %T')  preset=$PRESET  workers=$WORKERS  threads/worker=$THREADS"
  echo "[run] resolution=$RES  samples=$SPP  look=$LOOK  format=$FRAME_FORMAT  blur=$MOTION_BLUR"
  echo "[run] python=$PY"
  echo "=============================================================="
  nvidia-smi --query-gpu=index,name,memory.used,utilization.gpu \
             --format=csv,noheader 2>/dev/null | sed 's/^/  gpu: /'

  "$PY" "$RUNNER" \
    --preset "$PRESET" \
    --workers "$WORKERS" \
    --resolution "$RES" \
    --samples "$SPP" \
    --look "$LOOK" \
    --frame_format "$FRAME_FORMAT" \
    --motion_blur "$MOTION_BLUR" \
    --threads "$THREADS" \
    ${EXTRA[@]+"${EXTRA[@]}"}
  rc=$?

  echo "=============================================================="
  echo "[run] finished $(date '+%F %T')  exit=$rc"
  echo "=============================================================="
  exit $rc
} 2>&1 | tee -a "$LOG"

exit "${PIPESTATUS[0]}"
