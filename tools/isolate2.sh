#!/usr/bin/env bash
# Isolate the render SIGSEGV properly.
#
# The earlier attempt passed the wrong argument positions, so every case ran the
# same (invalid) config and "exit=0" meant nothing.  This version takes an
# explicit modality list and frame count and reports the real exit code.
#
# Hypothesis to test: the crash scales with FRAME COUNT (an accumulation /
# buffer-lifetime problem, like the EXR issue we fixed in our own pipeline),
# rather than being specific to depth or segmentation.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

run_case() {
  local tag="$1"; shift
  local mods="$1"; shift
  local frames="$1"; shift
  local spp="$1"; shift

  "$PY" - "$REPO" "$mods" "$frames" "$spp" <<'PY'
import sys, re, pathlib
repo, mods, frames, spp = sys.argv[1:5]
p = pathlib.Path(repo) / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"modalities: \[[^\]]*\]", f"modalities: [{mods}]", t)
t = re.sub(r"frame_count: \d+", f"frame_count: {frames}", t)
p.write_text(t)
q = pathlib.Path(repo) / "configs/server.yaml"
s = q.read_text()
s = re.sub(r"samples_per_pixel: \d+", f"samples_per_pixel: {spp}", s)
q.write_text(s)
PY

  "$BL" --background --factory-startup --python scripts/generate.py -- \
    --config configs/server.yaml --seed 1000 --variant x1 > "/tmp/case_$tag.log" 2>&1
  local rc=$?
  local out
  out=$(grep -oE 'rendered [0-9]+ frames|SAMPLE_OUTPUT=[^ ]*' "/tmp/case_$tag.log" | tail -1)
  printf '  %-24s mods=%-22s frames=%-4s spp=%-4s exit=%-4s %s\n' \
    "$tag" "$mods" "$frames" "$spp" "$rc" "${out:0:50}"
  if [ "$rc" -ne 0 ]; then
    tail -2 "/tmp/case_$tag.log" | sed 's/^/        /'
  fi
}

echo "=== frame-count sweep, RGB only ==="
run_case rgb_f1   rgb 1   32
run_case rgb_f8   rgb 8   32
run_case rgb_f32  rgb 32  32
run_case rgb_f81  rgb 81  32

echo
echo "=== all layers, escalating frame counts ==="
run_case all_f1   "rgb, depth, segmentation" 1  32
run_case all_f8   "rgb, depth, segmentation" 8  32
run_case all_f16  "rgb, depth, segmentation" 16 32
run_case all_f32  "rgb, depth, segmentation" 32 32
run_case all_f48  "rgb, depth, segmentation" 48 32
run_case all_f81  "rgb, depth, segmentation" 81 32
echo
echo "=== depth only vs seg only, 81 frames ==="
run_case dep_f81  depth 81 32
run_case seg_f81  segmentation 81 32
