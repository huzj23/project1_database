#!/usr/bin/env bash
# ===========================================================================
# Q1: will the "object too close to the frame edge" happen in a real run?
#
# My last outdoor renders used a HAND-WRITTEN probe camera (fixed position and
# 35 mm lens).  The real pipeline does not use a hand-set camera: it solves the
# camera from the trajectory.  This prints the gates that constrain it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== camera config (free_fall_gso.yaml) ==="
sed -n '/^camera:/,/^[a-z]/p' "$REPO/configs/scenarios/free_fall_gso.yaml" | sed 's/^/  /'

echo
echo "=== the framing gates enforced by the camera solver ==="
grep -rn 'min_object_frame_fraction\|max_object_frame_fraction\|trajectory_frame_fraction' \
    "$REPO/src/physim/camera/__init__.py" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== does the solver REJECT a framing it cannot satisfy? ==="
grep -rn 'cannot fit\|raise\|min_object_frame_fraction' \
    "$REPO/src/physim/camera/__init__.py" 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=== Q2: where is the table, and what furniture is near it? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
import numpy as np
WS = "/data/raw/huzijian/project1_database"
R = os.path.join(WS, "models/backgrounds/replicad")
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
print("  furniture instances near the table:")
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    tr = inst.get("translation", [0, 0, 0])
    if "table" in tpl.lower() or "chair" in tpl.lower():
        print(f"    {tpl:<34} translation={np.round(tr,3).tolist()}")
PY
