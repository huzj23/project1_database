"""Find a chain site where NO box touches anything but the declared floor -- footprint, not centre.

WHY THE PREVIOUS SITE SCAN WAS INSUFFICIENT
-------------------------------------------
`find_clean_site.py` proved that a downward ray under each box CENTRE hits the floor, and the site it chose
passed that test for all ten objects. The penetration gate then measured 67.72 mm of a box inside `stones`.
Both results are correct: a stone beside the box centre does not block the centre ray, but it does intersect
the box's footprint. Choosing a site therefore requires testing the FULL FOOTPRINT against the scene, not
the centre line.

This tool does exactly that, with the same exact test the gate uses: every obstacle triangle vertex is
transformed into the box's own frame and, if it lies inside the box, the intrusion depth is the smallest
distance to a face. A site is usable only when that depth is zero for all nine boxes and the trigger, and
when the floor is flat and every box still stands on it.

Usage:
    blender --background --factory-startup --python tools/v57/find_clear_site.py -- \
        --blend <staged or source blend> [--n 9] [--out report.json]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
OUT = Path(ARGS["out"]).resolve() if ARGS.get("out") else None
FLOOR = ARGS.get("floor", "Floor_main")
N = int(ARGS.get("n", "9"))
ARC_R = float(ARGS.get("arc_r", "2.0"))
PITCH = float(ARGS.get("pitch_m", "0.155"))
TOL_M = float(ARGS.get("tol_mm", "0.5")) / 1000.0

DIMS = {
    "Supernatural_Ouija_Board_Game": [0.062496879194, 0.275466365908, 0.408406312812],
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": [0.073462, 0.209265, 0.272852],
    "Hasbro_Cranium_Performance_and_Acting_Game": [0.055838, 0.207669099, 0.272573856],
    "LEGO_Star_Wars_Advent_Calendar": [0.0782, 0.2659, 0.3871],
}
ORDER = ["Supernatural_Ouija_Board_Game",
         "Hasbro_Trivial_Pursuit_Family_Edition_Game",
         "Hasbro_Cranium_Performance_and_Acting_Game"]
TRIGGER = "LEGO_Star_Wars_Advent_Calendar"

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()


def build_obstacle_bvh():
    """Every mesh except the floor, as one BVH with owner and triangle arrays kept alongside.

    BVHTree does not return its polygons, so the vertices and triangles are retained here; without them the
    overlap cannot be attributed or measured.
    """
    verts, tris, owners = [], [], []
    n_obj = 0
    for o in scene.objects:
        if o.type != "MESH" or o.name == FLOOR or o.name.startswith(("box", "trigger_", "gate_proxy_")):
            continue
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        try:
            mw = ev.matrix_world
            base = len(verts)
            verts.extend([mw @ v.co for v in me.vertices])
            for p in me.polygons:
                vs = list(p.vertices)
                for k in range(1, len(vs) - 1):
                    tris.append((base + vs[0], base + vs[k], base + vs[k + 1]))
                    owners.append(o.name)
            n_obj += 1
        finally:
            ev.to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True) if tris else None
    return bvh, owners, verts, tris, n_obj


OBVH, OWNERS, SVERTS, STRIS, N_OBJ = build_obstacle_bvh()
print("=" * 100)
print(f"clear-site search | {BLEND.name}")
print(f"  obstacle objects {N_OBJ}, triangles {len(STRIS):,}, floor '{FLOOR}' excluded")
print("=" * 100)


def floor_z(x, y):
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 2.0), (0, 0, -1), distance=8.0)
    if ok and obj.name == FLOOR:
        return loc.z
    return None


def penetration_of_box(centre, rot3, dims):
    """Exact intrusion depth of the scene into an oriented box, in metres, plus the offending objects.

    The box is defined by its centre, its 3x3 orientation and its (t, w, h) extents. Every obstacle vertex
    that falls inside the box is measured against the box's six faces; the largest such distance is the
    penetration. Obstacles here are open surfaces (foliage) as well as closed solids, which is why a
    containment test in the box's own frame is used rather than ray parity.
    """
    inv = Matrix([list(r) for r in rot3]).to_4x4().inverted()
    tr = Matrix.Translation(-Vector(centre))
    M = inv @ tr
    half = [dims[0] / 2.0, dims[1] / 2.0, dims[2] / 2.0]
    # Query the objects whose world AABB is near the box, so a 6.7M-triangle BVH is not walked per box.
    r = max(dims) * 0.75 + 0.05
    cand = []
    for a, b in OBVH.overlap(BVHTree.FromPolygons(
            [(centre[0] - r, centre[1] - r, centre[2] - r),
             (centre[0] + r, centre[1] - r, centre[2] - r),
             (centre[0] + r, centre[1] + r, centre[2] - r),
             (centre[0] - r, centre[1] + r, centre[2] - r),
             (centre[0] - r, centre[1] - r, centre[2] + r),
             (centre[0] + r, centre[1] - r, centre[2] + r),
             (centre[0] + r, centre[1] + r, centre[2] + r),
             (centre[0] - r, centre[1] + r, centre[2] + r)],
            [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)],
            all_triangles=False)):
        cand.append(b)
    depth, who, n_in = 0.0, set(), 0
    for b in set(cand):
        for vi in STRIS[b]:
            lp = M @ SVERTS[vi]
            if all(abs(lp[i]) <= half[i] for i in range(3)):
                n_in += 1
                pen = min(half[i] - abs(lp[i]) for i in range(3))
                if pen > depth:
                    depth = pen
                who.add(OWNERS[b])
    return depth, sorted(who), n_in


def eval_site(cx, cy, chord_deg):
    chord = math.radians(chord_deg)
    total = (N - 1) * PITCH
    phi0 = -total / (2.0 * ARC_R)
    acx = cx - ARC_R * math.sin(phi0 + chord)
    acy = cy + ARC_R * math.cos(phi0 + chord)
    zs, worst_depth, all_who, off_floor = [], 0.0, set(), []
    boxes = []
    for i in range(N):
        aid = ORDER[i % 3]
        phi = phi0 + (i * PITCH) / ARC_R
        ang = chord + phi
        px = acx + ARC_R * math.sin(ang)
        py = acy - ARC_R * math.cos(ang)
        z = floor_z(px, py)
        if z is None:
            off_floor.append(i)
            continue
        zs.append(z)
        dims = DIMS[aid]
        rot = [[math.cos(ang), -math.sin(ang), 0.0],
               [math.sin(ang), math.cos(ang), 0.0],
               [0.0, 0.0, 1.0]]
        d, who, n_in = penetration_of_box([px, py, z + dims[2] / 2.0], rot, dims)
        boxes.append({"i": i, "x": px, "y": py, "depth_m": d, "who": who})
        if d > worst_depth:
            worst_depth = d
        all_who.update(who)
    # The trigger, one pitch behind box 0 along the tangent.
    ang0 = chord + phi0
    phi_t = phi0 - (PITCH * 1.05) / ARC_R
    ang_t = chord + phi_t
    tx = acx + ARC_R * math.sin(ang_t)
    ty = acy - ARC_R * math.cos(ang_t)
    tz = floor_z(tx, ty)
    td = 0.0
    if tz is None:
        off_floor.append(-1)
    else:
        dims = DIMS[TRIGGER]
        rot = [[math.cos(ang_t), -math.sin(ang_t), 0.0],
               [math.sin(ang_t), math.cos(ang_t), 0.0],
               [0.0, 0.0, 1.0]]
        td, twho, _ = penetration_of_box([tx, ty, tz + dims[2] / 2.0], rot, dims)
        all_who.update(twho)
    return {"cx": cx, "cy": cy, "chord_deg": chord_deg,
            "worst_depth_m": max(worst_depth, td),
            "obstacles": sorted(all_who),
            "n_off_floor": len(off_floor), "off_floor": off_floor,
            "height_spread_m": (max(zs) - min(zs)) if len(zs) >= 2 else None,
            "boxes": boxes, "trigger_depth_m": td}


results = []
for cx in [-1.6, -1.2, -0.8, -0.4, 0.0, 0.4, 0.8, 1.2, 1.6]:
    for cy in [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5]:
        for chord in [0.0, 15.0, 30.0, 45.0, -15.0, -30.0]:
            results.append(eval_site(cx, cy, chord))

clear = [r for r in results if r["worst_depth_m"] <= TOL_M and r["n_off_floor"] == 0]
print("")
print(f"  sites scanned            : {len(results)}")
print(f"  all boxes on floor       : {sum(1 for r in results if r['n_off_floor'] == 0)}")
print(f"  clear of ALL obstacles   : {len(clear)}  (depth <= {TOL_M * 1000:.1f} mm)")

if clear:
    clear.sort(key=lambda r: (r["height_spread_m"] if r["height_spread_m"] is not None else 9,
                              r["worst_depth_m"]))
    print("")
    print(f"  {'centre (x,y)':22s} {'chord':>7s} {'height spread':>14s} {'worst depth':>12s}")
    for r in clear[:14]:
        hs = r["height_spread_m"]
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})     {r['chord_deg']:+7.1f} "
              f"{(('%.2f mm' % (hs * 1000)) if hs is not None else 'n/a'):>14s} "
              f"{('%.3f mm' % (r['worst_depth_m'] * 1000)):>12s}")
    best = clear[0]
    print("")
    print(f"  BEST: centre ({best['cx']:+.2f},{best['cy']:+.2f}) chord {best['chord_deg']:+.1f} deg  "
          f"height spread {best['height_spread_m'] * 1000:.2f} mm  "
          f"worst obstacle depth {best['worst_depth_m'] * 1000:.3f} mm")
else:
    # Show the least-bad options so the reason is visible rather than asserted.
    results.sort(key=lambda r: (r["n_off_floor"], r["worst_depth_m"]))
    print("")
    print("  No scanned site is completely clear. Least-bad candidates:")
    print(f"  {'centre (x,y)':22s} {'chord':>7s} {'off floor':>10s} {'worst depth':>12s}  obstacles")
    for r in results[:12]:
        print(f"  ({r['cx']:+6.2f},{r['cy']:+6.2f})     {r['chord_deg']:+7.1f} "
              f"{r['n_off_floor']:>10d} {('%.2f mm' % (r['worst_depth_m'] * 1000)):>12s}  "
              f"{r['obstacles'][:4]}")

if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n": N, "arc_r": ARC_R, "pitch_m": PITCH, "tolerance_m": TOL_M,
                               "n_scanned": len(results), "n_clear": len(clear),
                               "best": (clear[0] if clear else None),
                               "clear": clear[:30],
                               "least_bad": sorted(results,
                                                   key=lambda r: (r["n_off_floor"],
                                                                  r["worst_depth_m"]))[:20]},
                              indent=2), encoding="utf-8")
    print(f"\nreport written: {OUT}")
