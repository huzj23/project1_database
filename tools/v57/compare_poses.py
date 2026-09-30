"""Compare the SCAN's predicted box pose against the pose the BUILD actually produced.

WHY
---
The scan reported zero obstacle overlap at (-1.10, +11.70) chord +33, but the authoritative clearance check
on the built blend found box7 overlapping `leaves` 16 times. Since the scan tests the visual's oriented AABB,
which CONTAINS the visual mesh, the scan must have been testing a box in a different place from the one that
was built. This prints both, per box, so the discrepancy is a number rather than a suspicion:

    * scan  : the pose from tools/v57/scan_sites.py's own arc formula
    * build : the pose of the object actually in the blend

Any systematic offset shows up as a consistent column, and an offset in one axis names the bug.

Usage:
    blender --background --factory-startup --python tools/v57/compare_poses.py -- \
        --blend <built.blend> --site tools/v57/site_arc02.json --proxies <dir>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "v56"))
from box_visual import import_asset_object  # noqa: E402

BLEND = Path(ARGS["blend"]).resolve()
SITE = json.loads(Path(ARGS["site"]).read_text(encoding="utf-8"))
PROXY_DIR = Path(ARGS["proxies"]).resolve()
N = int(ARGS.get("n", "9"))
ARC_R = float(ARGS.get("arc_r", "2.0"))
PITCH = float(ARGS.get("pitch_m", "0.155"))

DIMS = {
    "Supernatural_Ouija_Board_Game": [0.062496879194, 0.275466365908, 0.408406312812],
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": [0.073462, 0.209265, 0.272852],
    "Hasbro_Cranium_Performance_and_Acting_Game": [0.055838, 0.207669099, 0.272573856],
    "LEGO_Star_Wars_Advent_Calendar": [0.0782, 0.2659, 0.3871],
}
ORDER = ["Supernatural_Ouija_Board_Game",
         "Hasbro_Trivial_Pursuit_Family_Edition_Game",
         "Hasbro_Cranium_Performance_and_Acting_Game"]
SHORT = {"Supernatural_Ouija_Board_Game": "Ouija",
         "Hasbro_Trivial_Pursuit_Family_Edition_Game": "Trivial",
         "Hasbro_Cranium_Performance_and_Acting_Game": "Cranium"}

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

# The scan's own prediction, repeated here verbatim so the comparison is against the same formula.
cx, cy = SITE["cx"], SITE["cy"]
chord = math.radians(SITE["chord_deg"])
total = (N - 1) * PITCH
phi0 = -total / (2.0 * ARC_R)
acx = cx - ARC_R * math.sin(phi0 + chord)
acy = cy + ARC_R * math.cos(phi0 + chord)

print("=" * 112)
print(f"scan prediction vs build | site ({cx:+.3f},{cy:+.3f}) chord {SITE['chord_deg']:+.1f}")
print("=" * 112)


def floor_z(x, y):
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 2.0), (0, 0, -1), distance=8.0)
    return loc.z if (ok and obj.name == "Floor_main") else None


print(f"  {'box':6s} {'predicted centre (x,y,z)':34s} {'built centre (x,y,z)':34s} {'delta (mm)':>22s}")
maxd = 0.0
for i in range(N):
    aid = ORDER[i % len(ORDER)]
    ang = chord + phi0 + (i * PITCH) / ARC_R
    px = acx + ARC_R * math.sin(ang)
    py = acy - ARC_R * math.cos(ang)
    z = floor_z(px, py)
    pred = [px, py, (z if z is not None else float("nan")) + DIMS[aid][2] / 2.0]

    o = next((x for x in scene.objects if x.name.startswith(f"box{i}_")), None)
    if o is None:
        print(f"  box{i}  MISSING")
        continue
    # The built object's visual AABB centre, which is what the scan compares against the obstacles.
    ws = [o.matrix_world @ v.co for v in o.data.vertices]
    bctr = [ (min(p[k] for p in ws) + max(p[k] for p in ws)) / 2.0 for k in range(3)]
    d = [ (bctr[k] - pred[k]) * 1000 for k in range(3)]
    maxd = max(maxd, max(abs(v) for v in d))
    print(f"  box{i}  ({pred[0]:8.4f},{pred[1]:9.4f},{pred[2]:7.4f})   "
          f"({bctr[0]:8.4f},{bctr[1]:9.4f},{bctr[2]:7.4f})   "
          f"({d[0]:+7.2f},{d[1]:+7.2f},{d[2]:+7.2f})")

# Also compare the import frame the scan uses against the one in the blend, since a differing frame would
# place the AABB's corners differently even at an identical centre.
print("")
print("  orientation check (local axes of the built object vs the imported frame):")
for i in (0, 7):
    aid = ORDER[i % len(ORDER)]
    o = next((x for x in scene.objects if x.name.startswith(f"box{i}_")), None)
    if o is None:
        continue
    tmp, rep = import_asset_object(aid, ROOT / "models" / "gso", DIMS[aid], f"cmp_{aid}")
    built = o.matrix_world.to_3x3()
    imported = tmp.matrix_world.to_3x3()
    # Compare the two rotation parts up to the yaw difference.
    yb = math.degrees(math.atan2(built[1][0], built[0][0]))
    yi = math.degrees(math.atan2(imported[1][0], imported[0][0]))
    print(f"    box{i} built yaw {yb:+8.3f}  import-frame yaw {yi:+8.3f}  difference {yb - yi:+8.3f}")
    bpy.data.objects.remove(tmp, do_unlink=True)

print("")
print(f"  worst axis disagreement: {maxd:.2f} mm")
