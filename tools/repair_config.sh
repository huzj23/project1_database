#!/usr/bin/env bash
# Repair configs/server.yaml after the isolation sweep left samples_per_pixel
# empty (the regex substitution wrote a bare key, which YAML reads as None).
#
# The mentor's production default is 128 spp with adaptive sampling + denoising.
# We start at 24 for smoke runs because our renderer is CPU-only and 128 spp on
# 1280x720 would make each smoke sample very slow; raise it for real batches.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

SPP="${1:-24}"
"$PY" - "$REPO" "$SPP" <<'PY'
import sys, re, pathlib
repo, spp = sys.argv[1], sys.argv[2]
p = pathlib.Path(repo) / "configs/server.yaml"
t = p.read_text()
if re.search(r"^samples_per_pixel:", t, re.M):
    t = re.sub(r"^samples_per_pixel:.*$", f"samples_per_pixel: {spp}", t, flags=re.M)
else:
    t = t.replace("render:\n", f"render:\n  samples_per_pixel: {spp}\n", 1)
p.write_text(t)
print("  samples_per_pixel ->", spp)
PY

# also make sure the scenario config is back to the full production shape
"$PY" - "$REPO" <<'PY'
import sys, re, pathlib
repo = sys.argv[1]
p = pathlib.Path(repo) / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"modalities: \[[^\]]*\]", "modalities: [rgb, depth, segmentation]", t)
t = re.sub(r"frame_count: \d+", "frame_count: 81", t)
p.write_text(t)
print("  modalities -> [rgb, depth, segmentation], frame_count -> 81")
PY

echo
echo "=== restoring server.yaml scenario_config ==="
"$PY" - "$REPO" <<'PY'
import sys, re, pathlib
repo = sys.argv[1]
p = pathlib.Path(repo) / "configs/server.yaml"
t = p.read_text()
t = re.sub(r"scenario_config: .*", "scenario_config: configs/scenarios/free_fall_gso.yaml", t)
p.write_text(t)
print("  ok")
PY

echo
echo "=== verifying ==="
"$PY" - "$REPO" <<'PY'
import sys, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
c = yaml.safe_load(open(repo / "configs/server.yaml"))
s = yaml.safe_load(open(repo / "configs/scenarios/free_fall_gso.yaml"))
print("  samples_per_pixel:", c["render"]["samples_per_pixel"])
print("  device           :", c["render"].get("device"))
print("  modalities       :", s["output"]["modalities"])
print("  frame_count      :", s["timing"]["frame_count"])
print("  resolution       :", s["output"]["resolution"])
print("  asset_ids        :", s["selection"]["asset_ids"])
print("  map_ids          :", s["selection"]["map_ids"])
PY
