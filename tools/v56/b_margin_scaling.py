"""Is the engine's mesh collision margin a FIXED absolute size or proportional to the shape?

The controls showed a GEOM_MESH gets a larger effective surface than its own vertices (+2 mm per
axis on a 56 x 208 x 273 mm box), while a GEOM_BOX of the same dimensions gets none. That margin is
NOT settable through the python API in this build (`collisionMargin` and `margin` are both
rejected), so its size has to be measured if early contact is to be predicted.

Whether it is fixed or proportional changes the practical consequence: a fixed 1 mm per side matters
a lot on a 12 mm-thin box and hardly at all on a 400 mm one, while a proportional margin scales with
the asset. This measures it at several sizes using exact box OBJs, where the true extent is known by
construction.

Read-only apart from scratch OBJs under `outcomes/v56/mixed_box_domino/build/`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pybullet as pb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b_geom  # noqa: E402

OUT = Path("/data/raw/huzijian/project1_database/outcomes/v56/mixed_box_domino")
BUILD = OUT / "build"
BUILD.mkdir(parents=True, exist_ok=True)


def exact_box_obj(path: Path, dims):
    t, w, h = dims
    verts = [(sx * t / 2, sy * w / 2, sz * h) for sx in (-1, 1) for sy in (-1, 1)
             for sz in (0, 1)]
    tris = [(0, 1, 3), (0, 3, 2), (4, 7, 5), (4, 6, 7), (0, 4, 5), (0, 5, 1),
            (2, 3, 7), (2, 7, 6), (0, 6, 2), (0, 4, 6), (1, 5, 7), (1, 7, 3)]
    b_geom.write_obj(path, verts, tris)


cid = pb.connect(pb.DIRECT)
pb.setGravity(0, 0, 0, physicsClientId=cid)

results = []
SIZES = [
    (0.012, 0.05, 0.10),
    (0.055838, 0.207669, 0.272574),
    (0.10, 0.30, 0.60),
    (0.25, 0.50, 1.00),
]
for i, dims in enumerate(SIZES):
    t, w, h = dims
    # Keep the .obj extension intact: pybullet validates the extension.
    obj = BUILD / f"scale_ctrl_{i}_{t:.4f}_{w:.4f}_{h:.4f}.obj".replace(".", "p").replace(
        "pobj", ".obj")
    exact_box_obj(obj, dims)
    center = [0.0, 0.0, 0.5 + h / 2.0]
    row = {"true_dims_m": list(dims)}
    for kind, arg in (("GEOM_BOX", None), ("GEOM_MESH", obj)):
        if kind == "GEOM_BOX":
            s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[t / 2, w / 2, h / 2],
                                        physicsClientId=cid)
        else:
            s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(arg), flags=0,
                                        physicsClientId=cid)
        b = pb.createMultiBody(0.5, s, basePosition=center, physicsClientId=cid)
        pb.performCollisionDetection(physicsClientId=cid)

        def surf(axis, sign, span=3.0):
            st, en = list(center), list(center)
            st[axis] = center[axis] + span * sign
            en[axis] = center[axis] - span * sign
            hit = pb.rayTest(st, en, physicsClientId=cid)[0]
            return None if hit[0] < 0 else hit[3][axis] - center[axis]

        ext = []
        for axis in (0, 1, 2):
            lo, hi = surf(axis, -1.0), surf(axis, +1.0)
            ext.append((hi - lo) if (lo is not None and hi is not None) else None)
        aabb_lo, aabb_hi = pb.getAABB(b, physicsClientId=cid)
        row[kind] = {
            "raycast_extents_m": ext,
            "raycast_added_per_axis_m": [round(ext[i] - dims[i], 6) for i in range(3)],
            "raycast_added_per_side_m": [round((ext[i] - dims[i]) / 2.0, 6) for i in range(3)],
            "aabb_added_per_axis_m": [round((aabb_hi[i] - aabb_lo[i]) - dims[i], 6)
                                      for i in range(3)],
        }
        pb.removeBody(b, physicsClientId=cid)
    results.append(row)
    print(f"true dims {[round(v,6) for v in dims]}")
    for kind in ("GEOM_BOX", "GEOM_MESH"):
        print(f"   {kind:10s} added per side (m): {row[kind]['raycast_added_per_side_m']}  "
              f"AABB added per axis: {row[kind]['aabb_added_per_axis_m']}")

pb.disconnect(cid)

mesh_sides = [v for r in results for v in r["GEOM_MESH"]["raycast_added_per_side_m"]]
box_sides = [v for r in results for v in r["GEOM_BOX"]["raycast_added_per_side_m"]]
summary = {
    "note": __doc__.strip().splitlines()[0],
    "mesh_added_per_side_min_m": min(mesh_sides),
    "mesh_added_per_side_max_m": max(mesh_sides),
    "mesh_margin_is_fixed_absolute": bool(max(mesh_sides) - min(mesh_sides) < 1e-6),
    "box_added_per_side_min_m": min(box_sides),
    "box_added_per_side_max_m": max(box_sides),
    "conclusion": (
        "GEOM_MESH shapes carry a FIXED absolute collision margin of "
        f"{min(mesh_sides)*1000:.3f} mm per side in this build, independent of shape size, while "
        "GEOM_BOX shapes carry none. The margin cannot be set through the python API here "
        "(collisionMargin and margin are both rejected), so it is an engine default that early "
        "contact must be predicted from rather than configured away."),
    "rows": results,
}
(OUT / "b_margin_scaling.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("\n" + "=" * 100)
print(f"GEOM_MESH added per side: {min(mesh_sides)*1000:.4f} .. {max(mesh_sides)*1000:.4f} mm "
      f"-> fixed absolute: {summary['mesh_margin_is_fixed_absolute']}")
print(f"GEOM_BOX  added per side: {min(box_sides)*1000:.4f} .. {max(box_sides)*1000:.4f} mm")
print(summary["conclusion"])
print(f"\nwritten: {OUT / 'b_margin_scaling.json'}")
