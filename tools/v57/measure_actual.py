"""Measure the boxes AS THEY ACTUALLY ARE in a built blend, against the obstacles. No placement model.

WHY THIS EXISTS
---------------
Two tools disagreed about the same site: `scan_sites.py` computed the boxes from the arc parameters and
reported zero intrusion, while `gate_penetration.py` measured the objects that were actually built and
reported 9.91 mm of a box inside `stones`. Exactly one of them can be right, and the difference has to be a
difference in POSE, because both now use the same asset frames and the same intrusion test.

This removes every assumption by measuring the built objects themselves. It reports, per box:

  * the world position of the object's origin and of its footprint centre -- if these differ, then seating a
    box using a ray at one of them measures the floor at a different place than the other, which is the
    likely origin of the disagreement;
  * the floor height under BOTH points, which exposes a sloped or stepped floor;
  * the intrusion depth into the obstacles at the real pose.

Usage:
    blender --background --factory-startup --python tools/v57/measure_actual.py -- \
        --blend <built blend> [--floor Floor_main]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

BLEND = Path(ARGS["blend"]).resolve()
FLOOR = ARGS.get("floor", "Floor_main")
OUT = Path(ARGS["out"]).resolve() if ARGS.get("out") else None

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

ANIM_PREFIX = ("box", "trigger_")
anims = [o for o in scene.objects
         if o.type == "MESH" and o.name.startswith(ANIM_PREFIX)
         and not o.name.startswith("gate_proxy_")]

# Obstacles: everything except the floor and the animated bodies themselves.
verts, tris, owners = [], [], []
for o in scene.objects:
    if o.type != "MESH" or o.name == FLOOR or o in anims:
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
    finally:
        ev.to_mesh_clear()
OBVH = BVHTree.FromPolygons(verts, tris, all_triangles=True)

print("=" * 118)
print(f"ACTUAL measured geometry | {BLEND.name}")
print(f"  obstacles {len(set(owners))}  triangles {len(tris):,}  animated bodies {len(anims)}")
print("=" * 118)


def floor_at(x, y):
    """The floor height under (x, y), and what was hit first -- the first hit matters, because an obstacle
    above the floor is what a seating ray would land on instead."""
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 2.0), (0, 0, -1), distance=8.0)
    if not ok:
        return None, "<nothing>"
    if obj.name == FLOOR:
        return loc.z, FLOOR
    # An obstacle was hit first; keep going below it to find the floor.
    ok2, loc2, n2, i2, o2, m2 = scene.ray_cast(deps, (x, y, loc.z - 1e-4), (0, 0, -1), distance=8.0)
    if ok2 and o2.name == FLOOR:
        return loc2.z, f"{obj.name} then {FLOOR}"
    return None, f"{obj.name} (no floor below)"


rows = []
worst = 0.0
for o in sorted(anims, key=lambda x: x.name):
    mw = o.matrix_world
    ws = [mw @ v.co for v in o.data.vertices]
    lo = Vector((min(p[i] for p in ws) for i in range(3)))
    hi = Vector((max(p[i] for p in ws) for i in range(3)))
    origin = mw.translation
    centre_xy = ((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0)
    fz_origin, who_origin = floor_at(origin.x, origin.y)
    fz_centre, who_centre = floor_at(*centre_xy)

    # Intrusion of the obstacles into this object's world AABB, in the object's own local frame.
    probe = BVHTree.FromPolygons(
        [(lo.x, lo.y, lo.z), (hi.x, lo.y, lo.z), (hi.x, hi.y, lo.z), (lo.x, hi.y, lo.z),
         (lo.x, lo.y, hi.z), (hi.x, lo.y, hi.z), (hi.x, hi.y, hi.z), (lo.x, hi.y, hi.z)],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)],
        all_triangles=False)
    # `overlap` returns (index_in_self, index_in_other); self is OBVH here, so the first element indexes the
    # obstacle triangles. Using the second element indexed the probe's own eight vertices against the
    # obstacle triangle array, which is how an earlier version reported zero intrusion for a box that the
    # authoritative world-space check shows overlapping `stones` 304 times.
    cand = {a for a, b in OBVH.overlap(probe)}
    inv = mw.inverted()
    lws = [v.co for v in o.data.vertices]
    llo = Vector((min(p[i] for p in lws) for i in range(3)))
    lhi = Vector((max(p[i] for p in lws) for i in range(3)))
    half = (lhi - llo) / 2.0
    ctr = (lhi + llo) / 2.0
    depth, who, n_in = 0.0, set(), 0
    for b in cand:
        for vi in tris[b]:
            lp = inv @ verts[vi]
            d = [lp[i] - ctr[i] for i in range(3)]
            if all(abs(d[i]) <= half[i] for i in range(3)):
                n_in += 1
                pen = min(half[i] - abs(d[i]) for i in range(3))
                if pen > depth:
                    depth = pen
                who.add(owners[b])
    worst = max(worst, depth)

    rows.append({
        "object": o.name,
        "origin_xy": [round(origin.x, 5), round(origin.y, 5)],
        "footprint_centre_xy": [round(centre_xy[0], 5), round(centre_xy[1], 5)],
        "origin_to_centre_mm": round(1000 * ((origin.x - centre_xy[0]) ** 2
                                             + (origin.y - centre_xy[1]) ** 2) ** 0.5, 3),
        "visual_base_z": round(lo.z, 6),
        "floor_z_under_origin": (round(fz_origin, 6) if fz_origin is not None else None),
        "floor_z_under_centre": (round(fz_centre, 6) if fz_centre is not None else None),
        "floor_obj_origin": who_origin,
        "floor_obj_centre": who_centre,
        "floor_slope_within_box_mm": (round(1000 * abs(fz_origin - fz_centre), 3)
                                      if (fz_origin is not None and fz_centre is not None) else None),
        "base_gap_mm": (round(1000 * (lo.z - fz_centre), 3) if fz_centre is not None else None),
        "intrusion_mm": round(1000 * depth, 4),
        "intrusion_by": sorted(who),
        "obstacle_vertices_inside": n_in,
    })

print("")
print(f"  {'object':22s} {'origin->centre':>15s} {'floor@origin':>13s} {'floor@centre':>13s} "
      f"{'slope':>8s} {'base gap':>9s} {'intrusion':>10s}  by")
for r in rows:
    print(f"  {r['object']:22s} {r['origin_to_centre_mm']:13.2f}mm "
          f"{(r['floor_z_under_origin'] if r['floor_z_under_origin'] is not None else float('nan')):13.5f} "
          f"{(r['floor_z_under_centre'] if r['floor_z_under_centre'] is not None else float('nan')):13.5f} "
          f"{(r['floor_slope_within_box_mm'] if r['floor_slope_within_box_mm'] is not None else float('nan')):7.2f}m "
          f"{(r['base_gap_mm'] if r['base_gap_mm'] is not None else float('nan')):8.2f}m "
          f"{r['intrusion_mm']:9.3f}m  {r['intrusion_by'][:3]}")

print("")
print(f"  worst intrusion across all bodies: {worst * 1000:.3f} mm")
if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"blend": str(BLEND), "worst_intrusion_mm": round(worst * 1000, 4),
                               "rows": rows}, indent=2), encoding="utf-8")
    print(f"  wrote {OUT}")
