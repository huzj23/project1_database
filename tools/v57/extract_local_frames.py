"""Extract each asset's authored local->world rotation and local AABB from the staged blend.

WHY THIS IS NEEDED
------------------
`find_clear_site.py` placed candidate boxes using a guessed local frame (it assumed the asset's height ran
along local Z). The imported GSO visuals do not use that convention -- the authored frames differ per asset --
so the scan tested boxes rotated 90 degrees from the ones that actually get built, and its "clear" verdicts
did not describe the real geometry. The gate, which uses each object's own `matrix_world`, reported the
truth: 9.91 mm of a box inside `stones` at a site the scan had called clear.

Rather than duplicate the import logic and hope it agrees, this reads the frames back out of the blend that
the real build produced. The residual rotation R0 (local -> world at zero yaw) and the local AABB are
constant per asset, so the scan can then compose them with any candidate yaw exactly as the build will.

Usage:
    blender --background --factory-startup --python tools/v57/extract_local_frames.py -- \
        --blend <staged.blend> --out local_frames.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
OUT = Path(ARGS["out"]).resolve()

bpy.ops.wm.open_mainfile(filepath=str(BLEND))

frames = {}
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    if not (o.name.startswith("box") or o.name.startswith("trigger_")):
        continue
    if o.name.startswith("gate_proxy_"):
        continue
    # The build places every box with a pure yaw about world Z, so removing that yaw from the object's world
    # matrix leaves the authored local frame, which is what is wanted and is yaw-independent.
    mw = o.matrix_world
    R = mw.to_3x3()
    yaw = math.atan2(R[1][0], R[0][0])
    Rz = [[math.cos(yaw), -math.sin(yaw), 0.0],
          [math.sin(yaw), math.cos(yaw), 0.0],
          [0.0, 0.0, 1.0]]
    # R0 = Rz^-1 @ R, as a list of row lists.
    RzT = [[Rz[j][i] for j in range(3)] for i in range(3)]
    Rl = [[sum(RzT[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    lws = [v.co for v in o.data.vertices]
    lo = [min(p[i] for p in lws) for i in range(3)]
    hi = [max(p[i] for p in lws) for i in range(3)]
    # The asset id is the trailing part after the first underscore.
    aid = o.name.split("_", 1)[1] if "_" in o.name else o.name
    rec = {
        "object": o.name,
        "yaw_deg": round(math.degrees(yaw), 9),
        "world_position_m": [round(v, 9) for v in mw.translation],
        "R0_local_to_world_at_zero_yaw": [[round(v, 9) for v in row] for row in Rl],
        "local_aabb_min_m": [round(v, 9) for v in lo],
        "local_aabb_max_m": [round(v, 9) for v in hi],
        "local_size_m": [round(hi[i] - lo[i], 9) for i in range(3)],
        "local_centre_m": [round((hi[i] + lo[i]) / 2.0, 9) for i in range(3)],
        "n_vertices": len(o.data.vertices),
    }
    key = aid
    if key in frames:
        # Two instances of the same asset must agree; a disagreement would mean the build is not placing all
        # copies with the same convention, which would invalidate using one frame per asset.
        prev = frames[key]
        same = (prev["local_size_m"] == rec["local_size_m"]
                and prev["R0_local_to_world_at_zero_yaw"] == rec["R0_local_to_world_at_zero_yaw"])
        rec["agrees_with_sibling"] = same
        if not same:
            print(f"  WARNING: {key} instances disagree; keeping the first")
            continue
    frames[key] = rec

print(f"assets found: {len(frames)}")
for k, v in frames.items():
    print(f"  {k:46s} local size {v['local_size_m']}  local centre {v['local_centre_m']}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(frames, indent=2), encoding="utf-8")
print(f"wrote {OUT}")
