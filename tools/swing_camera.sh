#!/usr/bin/env bash
# Put the furniture BEHIND the subject by swinging the camera to the other side.
#
# His camera sits at  centre + side * distance  with
#     side = (-direction[1], direction[0]),  flipped when side == "right".
# To land the camera on the +Y side (so it looks toward -Y, with the room's far
# furniture cluster as background) we need side = (0, +1), which means
# direction = (1, 0) -- i.e. 0 degrees -- and side: left.
#
# Previously direction was -90 deg, which placed the camera at -Y looking at a bare
# corridor: subject visible but nothing behind it.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"direction_degrees_range:\s*\[[^\]]*\]", "direction_degrees_range: [0.0, 0.0]", t)
t = re.sub(r"(\n\s*side:\s*)\w+", r"\g<1>left", t)
p.write_text(t)

import math
c = yaml.safe_load(open(p))
d = math.radians(c["physics"]["direction_degrees_range"][0])
side = (-math.sin(d), math.cos(d))
print(f"  direction : {c['physics']['direction_degrees_range']} deg")
print(f"  side      : {c['camera'].get('side')}")
print(f"  -> camera offset direction: ({side[0]:.2f}, {side[1]:.2f})")
print(f"     camera lands at +Y of the subject when side=(0,1)")
PY

echo
echo "=== run x0.5 (clean tree, self-verifying) ==="
bash "$WS/tools/clean_run.sh" 2>&1 | tail -20
