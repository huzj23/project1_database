"""Print the authored local frame of every box instance, to find why instances of one asset differ."""
import json
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

bpy.ops.wm.open_mainfile(filepath=str(Path(ARGS["blend"]).resolve()))

for o in sorted(bpy.data.objects, key=lambda x: x.name):
    if o.type != "MESH" or not (o.name.startswith("box") or o.name.startswith("trigger_")):
        continue
    if o.name.startswith("gate_proxy_"):
        continue
    mw = o.matrix_world
    R = mw.to_3x3()
    # scale per axis
    sc = [R.col[i].length for i in range(3)]
    yaw = math.atan2(R[1][0], R[0][0])
    lws = [v.co for v in o.data.vertices]
    lo = [min(p[i] for p in lws) for i in range(3)]
    hi = [max(p[i] for p in lws) for i in range(3)]
    # where does local +Z go in world?
    zw = (R @ __import__("mathutils").Vector((0, 0, 1))).normalized()
    xw = (R @ __import__("mathutils").Vector((1, 0, 0))).normalized()
    print(f"{o.name:26s} yaw={math.degrees(yaw):8.3f}  scale={[round(v,4) for v in sc]}  "
          f"size={[round(hi[i]-lo[i],4) for i in range(3)]}  "
          f"localX->world={[round(v,3) for v in xw]}  localZ->world={[round(v,3) for v in zw]}")
