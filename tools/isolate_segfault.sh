#!/usr/bin/env bash
# The smoke run now reaches rendering, then dies with SIGSEGV.
#
# We hit a very similar crash before in our own pipeline: reading several EXR
# layers and then doing further large numpy allocations.  Isolate whether the
# crash is modality-specific by rendering RGB only first, then adding layers back.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1

try_modalities() {
  local tag="$1" mods="$2" frames="$3" spp="$4"
  echo "--- $tag : modalities=$mods frames=$frames spp=$spp ---"
  "$PY" - "$REPO" "$mods" "$frames" "$spp" <<'PY'
import sys, re, pathlib
repo, mods, frames, spp = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
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
    --config configs/server.yaml --seed 1000 --variant x1 > /tmp/mod_$tag.log 2>&1
  local rc=$?
  echo "    exit=$rc"
  grep -oE "RENDER_DIAGNOSTICS=.*" /tmp/mod_$tag.log | head -c 160
  echo
  if [ $rc -ne 0 ]; then
    echo "    last lines:"
    tail -4 /tmp/mod_$tag.log | sed 's/^/      /'
  fi
  return $rc
}

try_modalities rgb 1 8
try_modalities rgbN 8 8
try_modalities depth 1 8
try_modalities seg 1 8
