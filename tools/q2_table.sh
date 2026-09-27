#!/usr/bin/env bash
# ===========================================================================
# Q2: put the turntable BACK ON THE TABLE, and find out why it clipped furniture.
#
# The user is right on both counts:
#   1. the turntable belongs ON THE TABLE (that was the frozen decision)
#   2. my last render put it on the FLOOR and it intersected furniture
#   3. I changed far more than "delete the useless patch ground"
#
# What actually needed to change was ONE thing: the collision proxy had to cover
# the scene's real floor.  The table placement was never broken.  Let me revert to
# the table and work out the clipping properly.
#
# The clipping happened because I placed the disc at the living-room point
# (1.00, -4.30) which is a FLOOR region, not the table.  The table is at
# (0.41, 0.17) with top z=0.758 -- a different place entirely.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
import numpy as np
WS = "/data/raw/huzijian/project1_database"
R = os.path.join(WS, "models/backgrounds/replicad")
cfg = json.load(open(os.path.join(R, "configs/scenes/apt_0.scene_instance.json")))
print("  === all furniture with translation, near the table area ===")
rows = []
for inst in cfg.get("object_instances", []):
    tpl = inst["template_name"].split("/")[-1]
    tr = inst.get("translation", [0, 0, 0])
    rows.append((tpl, float(tr[0]), float(tr[1]), float(tr[2])))
# habitat -> blender: (x, y, z)_hab -> (x, -z, y)_blender
print(f"  {'template':<40}{'hab_x':>9}{'hab_y':>9}{'hab_z':>9}  -> blender(x,y)")
for tpl, x, y, z in sorted(rows):
    if any(k in tpl.lower() for k in ("table", "chair", "sofa", "cabinet", "shelf")):
        print(f"  {tpl:<40}{x:>9.3f}{y:>9.3f}{z:>9.3f}  -> ({x:+.2f},{ -z:+.2f})")
print()
print(f"  total instances: {len(rows)}")
PY
