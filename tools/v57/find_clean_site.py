"""Find a chain site where EVERY box lands on the declared floor, by scanning the visible pavement.

WHY THIS EXISTS
---------------
The first V5.7 arc build was refused by its own gate: box 3 at (-0.045, +8.311) had `leaves` under it, not
`Floor_main`. That is the correct behaviour -- the plan forbids seating a box on an undeclared support and
forbids filling a hole with an invisible platform -- but it means the site must be chosen so that all nine
box footprints, plus the trigger, land on real pavement.

A fitted plane hides exactly this: the plane says "flat" while the actual ray under a given box hits
foliage. So the search must test the real ray for every box of a candidate chain, at the candidate's own
positions, and report which object each box stands on.

This scans candidate chain centres and orientations over the visible pavement and reports, for each, the
support object under every box. Only sites where all of them are the declared floor are usable.

Usage:
    blender --background --factory-startup --python tools/v57/find_clean_site.py -- \
        --blend <source.blend> [--n 9] [--arc-r 2.0] [--spacing 0.155]
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
N = int(ARGS.get("n", "9"))
ARC_R = float(ARGS.get("arc_r", "2.0"))
SPACING = float(ARGS.get("spacing", "0.155"))
FLOOR = ARGS.get("floor", "Floor_main")
OUT = Path(ARGS["out"]).resolve() if ARGS.get("out") else None

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

print("=" * 104)
print(f"clean-site scan | N={N}, arc R={ARC_R}, spacing={SPACING}, floor={FLOOR}")
print("=" * 104)


def support_at(x, y):
    """What the floor ray from z=1.5 hits at (x, y), and its height."""
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 1.5), (0.0, 0.0, -1.0), distance=6.0)
    if not ok:
        return None, "<nothing>"
    return loc.z, obj.name


def eval_site(cx, cy, chord_deg, arc_r):
    """Support and flatness for a chain centred at (cx, cy) with the given chord angle."""
    chord = math.radians(chord_deg)
    total = (N - 1) * SPACING
    phi0 = -total / (2.0 * arc_r)
    # The arc's centre lies perpendicular to the start tangent, so the chain curves across the site.
    arc_cx = cx - arc_r * math.sin(phi0 + chord)
    arc_cy = cy + arc_r * math.cos(phi0 + chord)
    zs = []
    objs = {}
    details = []
    for i in range(N):
        phi = phi0 + (i * SPACING) / arc_r
        ang = chord + phi
        px = arc_cx + arc_r * math.sin(ang)
        py = arc_cy - arc_r * math.cos(ang)
        z, nm = support_at(px, py)
        objs[nm] = objs.get(nm, 0) + 1
        if z is not None:
            zs.append(z)
        details.append({"i": i, "x": px, "y": py, "z": z, "obj": nm})
    # Trigger position, one spacing behind box 0.
    phi_t = phi0 - (SPACING * 1.05) / arc_r
    ang_t = chord + phi_t
    tx = arc_cx + arc_r * math.sin(ang_t)
    ty = arc_cy - arc_r * math.cos(ang_t)
    tz, tnm = support_at(tx, ty)
    objs[tnm] = objs.get(tnm, 0) + 1
    if tz is not None:
        zs.append(tz)
    all_floor = set(objs.keys()) == {FLOOR}
    spread = (max(zs) - min(zs)) if len(zs) >= 2 else None
    return {"cx": cx, "cy": cy, "chord_deg": chord_deg, "arc_r": arc_r,
            "objects": objs, "all_on_floor": all_floor,
            "n_on_floor": objs.get(FLOOR, 0), "n_positions": N + 1,
            "height_spread_m": spread, "details": details,
            "trigger": {"x": tx, "y": ty, "z": tz, "obj": tnm}}


results = []
# Scan centres over the visible pavement and a few chord orientations. The pavement seen by the authored
# camera spans x -2.68..+2.85 with usable y from about +6 to +14.
for cx in [-1.2, -0.8, -0.4, 0.0, 0.4, 0.8]:
    for cy in [6.6, 7.4, 8.2, 9.0, 9.8, 10.6, 11.4, 12.2]:
        for chord in [0.0, 15.0, -15.0, 30.0, -30.0]:
            r = eval_site(cx, cy, chord, ARC_R)
            results.append(r)

good = [r for r in results if r["all_on_floor"]]
print("")
print(f"  sites scanned          : {len(results)}")
print(f"  sites fully on {FLOOR}: {len(good)}")
if good:
    good.sort(key=lambda r: (r["height_spread_m"] if r["height_spread_m"] is not None else 9))
    print("")
    print(f"  {'centre (x,y)':24s} {'chord':>7s} {'n floor':>8s} {'height spread':>15s}  objects")
    for r in good[:12]:
        # Precompute the spread string: a nested same-type quote inside an f-string is a syntax error
        # before Python 3.12, and this file must run under the 3.9 interpreter bundled with the tooling.
        sp = r["height_spread_m"]
        sps = "n/a" if sp is None else "%.2f mm" % (sp * 1000)
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})       {r['chord_deg']:+7.1f} "
              f"{r['n_on_floor']:3d}/{r['n_positions']:<4d} {sps:>15s}  {r['objects']}")
    best = good[0]
    print("")
    print(f"  BEST: centre ({best['cx']:+.2f},{best['cy']:+.2f}), chord {best['chord_deg']:+.1f} deg, "
          f"height spread {best['height_spread_m'] * 1000:.2f} mm")
    print(f"    per box: ")
    for d in best["details"]:
        print(f"      box{d['i']} ({d['x']:+7.3f},{d['y']:+7.3f}) z={d['z']:+.5f} {d['obj']}")
    print(f"      trigger ({best['trigger']['x']:+7.3f},{best['trigger']['y']:+7.3f}) "
          f"z={best['trigger']['z']:+.5f} {best['trigger']['obj']}")
else:
    print("")
    print("  No scanned site puts every box on the declared floor. Report this rather than seating boxes")
    print("  on undeclared supports; the arc must move, shrink, or use a different ground patch.")
    # Show the closest failures so the reason is visible.
    near = sorted(results, key=lambda r: -r["n_on_floor"])[:6]
    print("")
    print(f"  {'centre (x,y)':24s} {'chord':>7s} {'n floor':>8s}  objects")
    for r in near:
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})       {r['chord_deg']:+7.1f} "
              f"{r['n_on_floor']:3d}/{r['n_positions']:<4d}  {r['objects']}")

if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n": N, "arc_r": ARC_R, "spacing": SPACING,
                               "n_scanned": len(results), "n_good": len(good),
                               "best": (good[0] if good else None),
                               "good": good[:20]}, indent=2), encoding="utf-8")
    print(f"\nreport written: {OUT}")
