#!/usr/bin/env bash
# Dump the exact repr of the comment region so the replacement can match.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
"$WS/tools/conda_env/bin/python" - <<'PY'
lines = open("configs/maps.yaml").read().split("\n")
for i, ln in enumerate(lines):
    if "2.89 m^2 box proxy" in ln or "Extracted by geometry" in ln or "202 triangles" in ln \
       or "support body from this mesh" in ln or "triangles: 202" in ln:
        print(f"  line {i+1}: {ln!r}")
print("  ---")
print(f"  total lines: {len(lines)}")
PY
