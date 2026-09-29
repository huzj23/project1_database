"""V5.6 B: how big is the collision proxy really, compared with the visual mesh?

`getAABB` on the GSO collision hulls came back systematically larger than the meshes' own vertex
extents (about +4 mm on EVERY axis for every asset). That is either

  * pybullet inflating convex-hull shapes by a built-in collision margin, or
  * the hull genuinely extending past the mesh (impossible: a convex hull's extent along an axis IS
    the max/min of its vertices, so the two must be equal unless something adds to it).

Those two explanations are separable, and the difference matters for the deliverable, because
"the collider is bigger than the visual" would make boxes collide early and interpenetrate on
screen. The measurement that separates them:

  * the vertex extents of the mesh along each of its own axes (the TRUE hull extent);
  * the effective surface found by RAYCASTS through the body's mid-height along each of the six
    directions (the surface the solver actually collides with);
  * a control GEOM_BOX of known half-extents, and a control hand-made EXACT box OBJ as GEOM_MESH,
    so the engine's own baseline inflation is measured rather than assumed.

Item 5 of the brief also asks for visual vs collision dimensions per axis and the relative
difference. Those are measured on the SAME axes (the collision's own frame), because comparing each
mesh in its own frame is meaningless when the two frames are not aligned -- and the misalignment
itself is reported here too, since a rotated collider would show the box askew.

Read-only apart from scratch OBJs under `outcomes/v56/mixed_box_domino/build/`.
Writes `outcomes/v56/mixed_box_domino/b_proxy_size.json`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pybullet as pb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b_geom  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v56/mixed_box_domino"
BUILD = OUT / "build"
BUILD.mkdir(parents=True, exist_ok=True)

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]


def raycast_surface(cid, center, axis, sign, span=2.0):
    """Distance from `center` to the first surface along +/- `axis`."""
    start = list(center)
    end = list(center)
    start[axis] = center[axis] + span * sign
    end[axis] = center[axis] - span * sign
    hit = pb.rayTest(start, end, physicsClientId=cid)[0]
    if hit[0] < 0:
        return None
    return hit[3][axis] - center[axis]


def probe_shape(cid, shape, center):
    """Effective extents and AABB of a collision shape, via raycasts through `center`."""
    body = pb.createMultiBody(0.5, shape, basePosition=center, physicsClientId=cid)
    pb.performCollisionDetection(physicsClientId=cid)
    out = {"raycast": {}, "aabb_dims": None}
    names = {0: "x_thickness", 1: "y_width", 2: "z_height"}
    for axis in (0, 1, 2):
        minus = raycast_surface(cid, center, axis, -1.0)
        plus = raycast_surface(cid, center, axis, +1.0)
        out["raycast"][names[axis]] = {
            "minus_m": minus, "plus_m": plus,
            "extent_m": (plus - minus) if (minus is not None and plus is not None) else None,
        }
    lo, hi = pb.getAABB(body, physicsClientId=cid)
    out["aabb_dims"] = [hi[i] - lo[i] for i in range(3)]
    pb.removeBody(body, physicsClientId=cid)
    return out


report = {"note": __doc__.strip().splitlines()[0], "controls": {}, "assets": {}}

cid = pb.connect(pb.DIRECT)
pb.setGravity(0, 0, 0, physicsClientId=cid)          # pure geometry probe

# --- controls: what does the ENGINE add to a shape whose true size is known exactly? -------------
print("=" * 112)
print("CONTROLS: engine-added size on shapes of exactly known dimensions")
print("  a control GEOM_BOX and a control GEOM_MESH of the SAME outer dimensions are compared, so any")
print("  difference between them is the engine's treatment of meshes rather than geometry.")

CT = 0.055838
CW = 0.207669
CH = 0.272574
ctrl_center = [0.0, 0.0, 0.5]

s_box = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[CT / 2, CW / 2, CH / 2],
                                physicsClientId=cid)
r_box = probe_shape(cid, s_box, ctrl_center)

_exact = BUILD / "control_exact_box.obj"
b_geom.write_obj(_exact, [(sx * CT / 2, sy * CW / 2, sz * CH) for sx in (-1, 1)
                          for sy in (-1, 1) for sz in (0, 1)],
                 [(0, 1, 3), (0, 3, 2), (4, 7, 5), (4, 6, 7), (0, 4, 5), (0, 5, 1),
                  (2, 3, 7), (2, 7, 6), (0, 6, 2), (0, 4, 6), (1, 5, 7), (1, 7, 3)])
s_mesh = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(_exact), flags=0,
                                 physicsClientId=cid)
r_mesh = probe_shape(cid, s_mesh, ctrl_center)

true_dims = [CT, CW, CH]
for label, r in (("control GEOM_BOX", r_box), ("control GEOM_MESH (same dims)", r_mesh)):
    ray = [r["raycast"][k]["extent_m"] for k in ("x_thickness", "y_width", "z_height")]
    aabb = r["aabb_dims"]
    report["controls"][label] = {"true_dims_m": true_dims, "raycast_extents_m": ray,
                                 "aabb_dims_m": aabb}
    print(f"\n  {label}")
    print(f"    true dims         {[round(v, 6) for v in true_dims]}")
    print(f"    raycast extents   {[None if v is None else round(v, 6) for v in ray]}")
    print(f"    getAABB dims      {[round(v, 6) for v in aabb]}")
    print(f"    raycast - true    "
          f"{[None if v is None else round(v - true_dims[i], 6) for i, v in enumerate(ray)]}")
    print(f"    AABB - true       {[round(aabb[i] - true_dims[i], 6) for i in range(3)]}")

# --- the real assets ---------------------------------------------------------------------------
print("\n" + "=" * 112)
print("THE THREE ASSETS: true hull extent vs effective (raycast) surface vs AABB")
for aid in ASSETS:
    d = GSO / aid
    cverts, ctris, cinfo = b_geom.upright_vertices(d / "collision_geometry.obj")
    cobj = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(cobj, cverts, ctris)
    ct, cw, ch = cinfo["thickness_m"], cinfo["width_m"], cinfo["height_m"]

    s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(cobj), flags=0,
                               physicsClientId=cid)
    # center of the upright box in the probe world
    r = probe_shape(cid, s, [0.0, 0.0, 0.5 + ch / 2.0])

    ray = [r["raycast"][k]["extent_m"] for k in ("x_thickness", "y_width", "z_height")]
    aabb = r["aabb_dims"]
    true_dims = [ct, cw, ch]

    # The visual mesh, projected onto the COLLISION's own axes (the only meaningful comparison).
    cv, ctt, _ci = b_geom.upright_vertices(d / "collision_geometry.obj")
    vraw, vtris = b_geom.read_obj(d / "visual_geometry.obj")
    # Recover the collision's own frame, then project the RAW visual vertices onto those axes.
    axes = b_geom.box_frame(b_geom.tri_normal_area(*b_geom.read_obj(
        d / "collision_geometry.obj")), b_geom.read_obj(d / "collision_geometry.obj")[0])
    vis_proj = []
    for ax in axes:
        p = [b_geom.dot(v, ax) for v in vraw]
        vis_proj.append(max(p) - min(p))

    # Frame misalignment between the visual's own frame and the collision's own frame.
    vaxes = b_geom.box_frame(b_geom.tri_normal_area(vraw, vtris), vraw)
    angles = []
    for i, cax in enumerate(axes):
        best = max(abs(b_geom.dot(cax, vax)) for vax in vaxes)
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, best)))))

    rows = []
    for i, role in enumerate(("thickness_axis", "width_axis", "height_axis")):
        c_true = true_dims[i]
        c_eff = ray[i]
        c_aabb = aabb[i]
        v_ext = vis_proj[i]
        rows.append({
            "axis_index": i, "axis_role": role,
            "collision_true_extent_m": round(c_true, 6),
            "collision_effective_extent_m": (round(c_eff, 6) if c_eff is not None else None),
            "collision_aabb_extent_m": round(c_aabb, 6),
            "visual_extent_m": round(v_ext, 6),
            "engine_added_m": (round(c_eff - c_true, 6) if c_eff is not None else None),
            "aabb_added_m": round(c_aabb - c_true, 6),
            "collision_effective_minus_visual_m": (round(c_eff - v_ext, 6)
                                                   if c_eff is not None else None),
            "collision_effective_over_visual": (round(c_eff / v_ext, 5)
                                                if (c_eff and v_ext > 0) else None),
            "collision_much_bigger_than_visual_10pct": bool(
                c_eff is not None and v_ext > 0 and (c_eff - v_ext) / v_ext > 0.10),
        })

    engine_added = [x["engine_added_m"] for x in rows if x["engine_added_m"] is not None]
    aabb_added = [x["aabb_added_m"] for x in rows]
    report["assets"][aid] = {
        "true_hull_dims_t_w_h_m": true_dims,
        "effective_surface_dims_t_w_h_m": ray,
        "aabb_dims_m": aabb,
        "visual_projected_on_collision_axes_m": vis_proj,
        "per_axis": rows,
        "engine_added_per_axis_m": engine_added,
        "engine_added_uniform": bool(
            engine_added and (max(engine_added) - min(engine_added)) < 1e-9),
        "aabb_added_per_axis_m": aabb_added,
        "visual_collision_frame_misalignment_deg": [round(a, 4) for a in angles],
        "max_frame_misalignment_deg": round(max(angles), 4),
        "any_axis_over_10pct_bigger": any(x["collision_much_bigger_than_visual_10pct"]
                                          for x in rows),
    }

    print(f"\n  {aid}")
    print(f"    {'axis':14s} {'col_true':>10s} {'col_eff':>10s} {'col_aabb':>10s} "
          f"{'visual':>10s} {'eng_added':>10s} {'eff-vis':>10s} {'eff/vis':>8s}")
    for x in rows:
        print(f"    {x['axis_role']:14s} {x['collision_true_extent_m']:10.6f} "
              f"{str(x['collision_effective_extent_m']):>10s} "
              f"{x['collision_aabb_extent_m']:10.6f} {x['visual_extent_m']:10.6f} "
              f"{str(x['engine_added_m']):>10s} "
              f"{str(x['collision_effective_minus_visual_m']):>10s} "
              f"{str(x['collision_effective_over_visual']):>8s}")
    print(f"    engine added per axis (m): {engine_added}  uniform={report['assets'][aid]['engine_added_uniform']}")
    print(f"    AABB added per axis (m)  : {[round(v, 6) for v in aabb_added]}")
    print(f"    visual-vs-collision frame misalignment (deg): "
          f"{report['assets'][aid]['visual_collision_frame_misalignment_deg']}")

pb.disconnect(cid)

print("\n" + "=" * 112)
print("INTERPRETATION")
print("  'eng_added' = raycast surface minus the mesh's own vertex extent. A convex hull's extent is")
print("  exactly its vertex extent, so any positive value is size the ENGINE added, not geometry.")
print("  'eff-vis'   = the surface the solver collides with, minus the visual mesh on the same axes.")

(OUT / "b_proxy_size.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'b_proxy_size.json'}")
